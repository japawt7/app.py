import os
from flask import Flask, request, jsonify
import requests
from flask_cors import CORS

app = Flask(__name__)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
CORS(app, resources={r"/api/*": {"origins": allowed_origins.split(",") if "," in allowed_origins else [allowed_origins]}})

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "sportmonks-data.p.rapidapi.com")
BASE_URL = "https://sportmonks-data.p.rapidapi.com/football"

@app.route("/api/fixtures", methods=["GET"])
def get_fixtures():
    if not RAPIDAPI_KEY:
        return jsonify({"error": "RAPIDAPI_KEY is not configured", "data": []}), 500

    date_param = request.args.get("date", "2026-11-03")
    url = f"{BASE_URL}/fixtures/date/{date_param}"

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict) and payload.get("error"):
            return jsonify({"error": payload["error"], "data": []}), 502

        return jsonify(payload.get("data", payload))
    except requests.RequestException as exc:
        return jsonify({"error": str(exc), "data": []}), 502
    except ValueError:
        return jsonify({"error": "Invalid JSON from upstream API", "data": []}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
