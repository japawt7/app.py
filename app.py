from flask import Flask, request, jsonify
import requests
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/api/fixtures', methods=['GET'])
def get_fixtures():
    data_jogo = request.args.get('date', '2026-11-03')
    
    # Endpoint de consulta pública / API anterior
    url = f"https://api.football-data.org/v4/matches?dateFrom={data_jogo}&dateTo={data_jogo}"
    headers = { 'X-Auth-Token': 'TUA_CHAVE_ANTIGA_SE_TIVERES' }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e), "data": []}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
