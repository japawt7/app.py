import os, time, statistics
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, timedelta
import psycopg2, psycopg2.extras
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
# No Render, defina ALLOWED_ORIGINS com o endereço do seu site (ex.: https://meusite.com)
CORS(app, resources={r"/api/*": {"origins": os.environ.get("ALLOWED_ORIGINS", "*").split(",")}})

BASE = "https://v3.football.api-sports.io"
KEY = os.environ.get("APIFOOTBALL_KEY")      # NUNCA colocar a chave no código
DB_URL = os.environ.get("DATABASE_URL")      # Postgres (Supabase, Neon ou Render)
MAX_NEW = int(os.environ.get("MAX_NEW_PER_REQUEST", 15))  # protege sua cota diária
TZ = "America/Sao_Paulo"
LIVE_TTL = int(os.environ.get("LIVE_TTL", 60))  # segundos entre consultas de jogos ao vivo

TIPOS = {"Total Shots": "shots", "Shots on Goal": "sot", "Corner Kicks": "corners",
         "Offsides": "offsides", "Fouls": "fouls", "Yellow Cards": "yellow",
         "Red Cards": "red", "Ball Possession": "possession", "Goalkeeper Saves": "saves"}

_cache = {}


def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (time.time(), value)
    return value


def api(path, params):
    r = requests.get(BASE + path, headers={"x-apisports-key": KEY}, params=params, timeout=25)
    r.raise_for_status()
    j = r.json()
    if j.get("errors"):  # a API-Football devolve 200 mesmo com erro (plano, limite...)
        raise RuntimeError(str(j["errors"]))
    return j.get("response", [])


def q(sql, args=None, many=False):
    with closing(psycopg2.connect(DB_URL)) as conn:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if many:
                psycopg2.extras.execute_batch(cur, sql, args)
            else:
                cur.execute(sql, args)
            return cur.fetchall() if cur.description else None


_db_ok = False


def init_db():
    """Cria as tabelas na primeira vez que o banco é usado (não derruba o servidor se falhar)."""
    global _db_ok
    if _db_ok:
        return
    q("""CREATE TABLE IF NOT EXISTS games(
            id BIGINT PRIMARY KEY, played_at TEXT, league TEXT,
            home_id BIGINT, away_id BIGINT, home TEXT, away TEXT, hg INT, ag INT);
         CREATE TABLE IF NOT EXISTS stats(
            game_id BIGINT, team_id BIGINT, k TEXT, v DOUBLE PRECISION,
            PRIMARY KEY(game_id, team_id, k));""")
    _db_ok = True


def erro_txt(e):
    if isinstance(e, RuntimeError):
        return str(e)
    if isinstance(e, psycopg2.Error):
        return "erro no banco (confira se DATABASE_URL começa com postgresql://, sem aspas e sem a palavra psql)"
    return type(e).__name__


def num(v):
    if v is None:
        return 0.0
    try:
        return float(str(v).replace("%", ""))
    except ValueError:
        return None


def summarize(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    mode, count = Counter(round(v, 1) for v in vals).most_common(1)[0]
    return {"mean": round(statistics.mean(vals), 2), "median": round(statistics.median(vals), 2),
            "mode": mode if count > 1 else None}  # sem repetição = sem moda


def registrar(tid, venue):
    """Registra no banco os jogos finalizados da temporada atual do time. Retorna (ids, pendentes)."""
    init_db()
    # o plano grátis não aceita o parâmetro "last": busca os jogos do time por temporada
    hoje = date.today()
    seasons = [hoje.year] if hoje.month >= 7 else [hoje.year, hoje.year - 1]
    fx = []
    for ss in seasons:
        fx += cached(("team", tid, ss), 3600,
                     lambda ss=ss: api("/fixtures", {"team": tid, "season": ss, "timezone": TZ}))
    fx = [f for f in fx if f["fixture"]["status"]["short"] == "FT"]
    if not fx:
        return [], 0
    season = max(f["league"]["season"] for f in fx)
    fx = [f for f in fx if f["league"]["season"] == season]
    if venue in ("home", "away"):
        fx = [f for f in fx if f["teams"][venue]["id"] == tid]
    ids = [f["fixture"]["id"] for f in fx]
    have = {r["game_id"] for r in q("SELECT game_id FROM stats WHERE k='_ok' AND game_id = ANY(%s)", (ids,))}
    pend = [f for f in fx if f["fixture"]["id"] not in have]
    for f in pend[:MAX_NEW]:
        gid = f["fixture"]["id"]
        rows = [(gid, 0, "_ok", 1)]
        for t in api("/fixtures/statistics", {"fixture": gid}):
            for s in t["statistics"]:
                k = TIPOS.get(s["type"])
                if k:
                    rows.append((gid, t["team"]["id"], k, num(s["value"])))
        q("INSERT INTO games VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
          (gid, f["fixture"]["date"], f["league"]["name"], f["teams"]["home"]["id"], f["teams"]["away"]["id"],
           f["teams"]["home"]["name"], f["teams"]["away"]["name"], f["goals"]["home"], f["goals"]["away"]))
        q("INSERT INTO stats VALUES (%s,%s,%s,%s) ON CONFLICT (game_id,team_id,k) DO UPDATE SET v=EXCLUDED.v",
          rows, many=True)
    return ids, max(0, len(pend) - MAX_NEW)


def slim(t):
    return {k: t.get(k) for k in ("id", "name", "logo")}


def lg(l):
    return {k: l.get(k) for k in ("id", "name", "country", "logo")}


def card(f):
    s = f["fixture"]["status"]
    return {"id": f["fixture"]["id"], "date": f["fixture"]["date"], "ts": f["fixture"]["timestamp"],
            "status": s["short"], "elapsed": s["elapsed"], "goals": f["goals"], "league": lg(f["league"]),
            "home": slim(f["teams"]["home"]), "away": slim(f["teams"]["away"])}


@app.get("/api/fixtures")
def fixtures():
    if not KEY:
        return jsonify(error="Chave da API não configurada no servidor."), 500
    try:
        start = date.fromisoformat(request.args["start"])
        end = date.fromisoformat(request.args["end"])
    except (KeyError, ValueError):
        return jsonify(error="Use ?start=AAAA-MM-DD&end=AAAA-MM-DD"), 400
    if not 0 <= (end - start).days <= 7:
        return jsonify(error="Período máximo: 7 dias."), 400
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    def um_dia(d):
        try:
            fx = cached(("day", d), 120 if d == date.today() else 900,
                        lambda: api("/fixtures", {"date": d.isoformat(), "timezone": TZ}))
            return fx, None
        except (requests.RequestException, RuntimeError) as e:
            return [], f"{d.strftime('%d/%m')}: {e}"

    with ThreadPoolExecutor(max_workers=7) as ex:
        res = list(ex.map(um_dia, days))
    data = [f for fx, _ in res for f in fx]
    avisos = [e for _, e in res if e]
    if not data and avisos:
        return jsonify(error=f"Falha no fornecedor de dados: {avisos[0]}"), 502
    return jsonify(data=[card(f) for f in data], avisos=avisos[:3])


@app.get("/api/team/<int:tid>/stats")
def team_stats(tid):
    if not KEY or not DB_URL:
        return jsonify(error="Servidor sem APIFOOTBALL_KEY ou DATABASE_URL configurados."), 500
    venue = request.args.get("venue", "all")  # home | away | all (geral)
    if venue not in ("home", "away", "all"):
        return jsonify(error="venue deve ser home, away ou all"), 400
    try:
        ids, pendentes = registrar(tid, venue)
    except (requests.RequestException, RuntimeError, psycopg2.Error) as e:
        return jsonify(error=f"Falha ao registrar jogos: {erro_txt(e)}"), 502
    if not ids:
        return jsonify(games=0, total=0, pending=0, stats={})
    games = {g["id"]: g for g in q("SELECT * FROM games WHERE id = ANY(%s)", (ids,))}
    series = defaultdict(list)
    for g in games.values():
        own, opp = (g["hg"], g["ag"]) if g["home_id"] == tid else (g["ag"], g["hg"])
        series["goals"].append(own)
        series["opp_goals"].append(opp)
    for r in q("SELECT game_id,team_id,k,v FROM stats WHERE game_id = ANY(%s) AND k<>'_ok'", (ids,)):
        series[("" if r["team_id"] == tid else "opp_") + r["k"]].append(r["v"])
    return jsonify(games=len(games), total=len(ids), pending=pendentes,
                   stats={k: summarize(v) for k, v in series.items()})


@app.get("/api/team/<int:tid>/games")
def team_games(tid):
    """Jogos da temporada do time (mais recente primeiro), com estatísticas do time e do adversário."""
    if not KEY or not DB_URL:
        return jsonify(error="Servidor sem APIFOOTBALL_KEY ou DATABASE_URL configurados."), 500
    try:
        ids, pendentes = registrar(tid, "all")
    except (requests.RequestException, RuntimeError, psycopg2.Error) as e:
        return jsonify(error=f"Falha ao registrar jogos: {erro_txt(e)}"), 502
    if not ids:
        return jsonify(games=[], total=0, pending=0)
    st = defaultdict(lambda: defaultdict(dict))
    for r in q("SELECT game_id,team_id,k,v FROM stats WHERE game_id = ANY(%s) AND k<>'_ok'", (ids,)):
        st[r["game_id"]][r["team_id"]][r["k"]] = r["v"]
    out = []
    for g in q("SELECT * FROM games WHERE id = ANY(%s) ORDER BY played_at DESC", (ids,)):
        casa = g["home_id"] == tid
        own = dict(st[g["id"]].get(tid, {}))
        opp = dict(st[g["id"]].get(g["away_id"] if casa else g["home_id"], {}))
        own["goals"], opp["goals"] = (g["hg"], g["ag"]) if casa else (g["ag"], g["hg"])
        out.append({"date": g["played_at"], "home": casa, "opp": g["away"] if casa else g["home"],
                    "own": own, "opp_s": opp})
    return jsonify(games=out, total=len(ids), pending=pendentes)


@app.get("/api/live")
def live():
    """Jogos acontecendo agora (1 consulta compartilhada por todos os visitantes)."""
    if not KEY:
        return jsonify(error="Chave da API não configurada no servidor."), 500
    try:
        data = cached(("live",), LIVE_TTL, lambda: api("/fixtures", {"live": "all", "timezone": TZ}))
        return jsonify(data=[{"id": f["fixture"]["id"], "status": f["fixture"]["status"]["short"],
                              "elapsed": f["fixture"]["status"]["elapsed"], "goals": f["goals"]} for f in data])
    except (requests.RequestException, RuntimeError) as e:
        return jsonify(error=f"Falha no fornecedor de dados: {e}"), 502


@app.get("/api/fixture/<int:fid>")
def one_fixture(fid):
    if not KEY:
        return jsonify(error="Chave da API não configurada no servidor."), 500
    try:
        r = cached(("one", fid), 30, lambda: api("/fixtures", {"id": fid, "timezone": TZ}))
        return jsonify(data=card(r[0]) if r else None)
    except (requests.RequestException, RuntimeError) as e:
        return jsonify(error=f"Falha no fornecedor de dados: {e}"), 502


@app.get("/api/match/<int:fid>")
def match_stats(fid):
    """Estatísticas de um jogo (atualizadas pela API durante a partida). Cache curto, igual ao placar."""
    if not KEY:
        return jsonify(error="Chave da API não configurada no servidor."), 500
    try:
        st = cached(("mst", fid), LIVE_TTL, lambda: api("/fixtures/statistics", {"fixture": fid}))
        return jsonify(stats={str(t["team"]["id"]): {x["type"]: x["value"] for x in t["statistics"]} for t in st})
    except (requests.RequestException, RuntimeError) as e:
        return jsonify(error=f"Falha no fornecedor de dados: {e}"), 502


@app.get("/")
def home():
    return jsonify(status="online", system="Japa Pro I.A. Engine")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
