from flask import Flask, request, jsonify
import requests
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

# Chave da API configurada de forma segura nas variáveis de ambiente do Render ou por omissão
API_KEY = os.environ.get('SPORTMONKS_API_KEY', 'TUA_CHAVE_API')

@app.route('/api/fixtures', methods=['GET'])
def get_fixtures():
    data_jogo = request.args.get('date', '2026-11-03')
    
    # Endpoint oficial otimizado para recolher todas as partidas de uma data com os respetivos participantes e ligas
    url = f"https://api.sportmonks.com/v3/football/fixtures/date/{data_jogo}?api_token={API_KEY}&include=participants;league"
    
    try:
        response = requests.get(url, timeout=20)
        
        # Se a API externa responder com sucesso, repassamos os dados crus para o frontend
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({
                "error": f"Erro na API externa (Status: {response.status_code})",
                "data": []
            }), response.status_code
            
    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": f"Falha de conexão com a API: {str(e)}",
            "data": []
        }, 500)

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "online", "message": "Statspro AI Proxy Engine v2.10 Ativo"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
