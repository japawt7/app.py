import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "ea16720f23msh500da44d30818d3p1b63c3jsn4023d8e4a241")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "sportsmonks-data.p.rapidapi.com"
}

@app.route("/api/fixtures", methods=["GET"])
def get_fixtures():
    date_param = request.args.get("date")
    if not date_param:
        return jsonify({"status": "error", "message": "Parâmetro 'date' é obrigatório"}), 400

    url = f"https://sportsmonks-data.p.rapidapi.com/v3/football/fixtures/date/{date_param}"
    params = {"include": "participants;league;scores"}

    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
