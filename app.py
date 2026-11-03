from flask import Flask, request, jsonify
import requests
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# A tua chave RapidAPI visível nas imagens
RAPIDAPI_KEY = "ea16720f23msh500da44d30818d3p1b63c3sn4023d8e4a241"
RAPIDAPI_HOST = "sportmonks-data.p.rapidapi.com" # ou o host correto da API que estás a usar na RapidAPI

@app.route('/api/fixtures', methods=['GET'])
def get_fixtures():
    data_jogo = request.args.get('date', '2026-11-03')
    
    # Endpoint da SportMonks na RapidAPI para buscar os jogos por data
    url = f"https://sportmonks-data.p.rapidapi.com/football/fixtures/date/{data_jogo}"
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e), "data": []}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
