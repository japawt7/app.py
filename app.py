from flask import Flask, request, jsonify
import requests
from flask_cors import CORS
os = __import__('os')

app = Flask(__name__)
CORS(app)

# A tua chave da API guardada nas variáveis de ambiente do Render ou definida aqui
API_KEY = os.environ.get('SPORTMONKS_API_KEY', 'TUA_CHAVE_API')

@app.route('/api/fixtures', methods=['GET'])
def get_fixtures():
    data_jogo = request.args.get('date', '2026-11-03')
    
    # URL oficial para buscar todos os fixtures da data requisitada com inclusão de participantes e ligas
    url = f"https://api.sportmonks.com/v3/football/fixtures/date/{data_jogo}?api_token={API_KEY}&include=participants;league"
    
    try:
        response = requests.get(url, timeout=15)
        dados = response.json()
        return jsonify(dados)
    except Exception as e:
        return jsonify({"error": str(e), "data": []}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
