import os
import datetime
import uuid
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from bson import ObjectId

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
MONGO_CLIENT = None
app = Flask(__name__)

# CORS: Sta alles toe (beveiliging gebeurt in de proxy)
CORS(app, origins="*")

app.config['MONGO_URI'] = DEFAULT_MONGO_URI

# --- Database Connectie ---
def get_db():
    global MONGO_CLIENT
    if MONGO_CLIENT is None:
        try:
            MONGO_CLIENT = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=5000)
        except ConnectionFailure:
            return None
    return MONGO_CLIENT['data_store']

# --- Decorator: Alleen Client ID Check (Trust Mode) ---
def require_client_id(f):
    """
    Kijkt puur of de header aanwezig is.
    Er vindt GEEN validatie plaats of het ID 'bekend' is.
    We vertrouwen de upstream proxy.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Header van Proxy (of query param voor makkelijk testen)
        client_id = request.headers.get('x-client-id') or request.args.get('client_id')

        if not client_id:
            return jsonify({"error": "Missing x-client-id header"}), 400

        # Zet ID klaar voor gebruik in de functie
        g.client_id = client_id
        
        return f(*args, **kwargs)
    return decorated_function

# --- Rate Limiter ---
limiter = Limiter(key_func=get_remote_address, default_limits=["2000 per hour"])
limiter.init_app(app)

# --- JSON Serialisatie Helper ---
def format_mongo_doc(data):
    if isinstance(data, list):
        return [format_mongo_doc(item) for item in data]
    if isinstance(data, dict):
        new_doc = {}
        for key, value in data.items():
            if isinstance(value, ObjectId):
                new_doc[key] = str(value)
            elif isinstance(value, datetime.datetime):
                new_doc[key] = value.isoformat()
            elif isinstance(value, (dict, list)):
                new_doc[key] = format_mongo_doc(value)
            else:
                new_doc[key] = value
        if '_id' in new_doc:
            new_doc['id'] = new_doc.pop('_id')
        return new_doc
    return data

# --- Helper: Log Statistieken ---
def log_statistic(action, client_id, endpoint_name):
    db = get_db()
    if db:
        try:
            db.statistics.insert_one({
                'timestamp': datetime.datetime.utcnow(),
                'client_id': client_id,
                'endpoint': endpoint_name,
                'action': action
            })
        except: pass

# --- ROUTES: Dashboard ---

@app.route('/')
@app.route('/dashboard.html')
def serve_dashboard():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(root_dir, 'dashboard.html')

@app.route('/dashboard_data', methods=['GET'])
def dashboard_data():
    db = get_db()
    if db is None: return jsonify({'error': 'DB Error'}), 500

    # Haal clients op (puur voor weergave in dropdowns)
    clients = list(db.clients.find({}, {'description': 1, 'created_at': 1, '_id': 1}))
    
    # Haal collectie namen op
    cols = db.list_collection_names()
    endpoints = [c for c in cols if c not in ['clients', 'statistics', 'system.indexes']]

    return jsonify({
        'stats': {
            'total_calls': db.statistics.count_documents({}),
            'active_endpoints': len(endpoints),
            'known_clients': len(clients)
        },
        'clients': format_mongo_doc(clients),
        'endpoints': endpoints
    })

@app.route('/settings', methods=['POST', 'DELETE'])
def settings():
    """
    Beheert het 'Adresboek' van clients. 
    Genereert GEEN keys meer, alleen IDs voor administratie.
    """
    db = get_db()
    
    if request.method == 'POST':
        data = request.get_json()
        description = data.get('description', 'Nieuwe Client')
        # Maak een simpele leesbare ID of gebruik UUID
        new_id = str(uuid.uuid4())[:8] 

        db.clients.insert_one({
            '_id': new_id,
            'description': description,
            'created_at': datetime.datetime.utcnow()
        })
        return jsonify({'message': 'Client toegevoegd', 'client_id': new_id}), 201

    elif request.method == 'DELETE':
        data = request.get_json()
        db.clients.delete_one({'_id': data.get('client_id')})
        return jsonify({'message': 'Client verwijderd'}), 200

# --- ROUTES: API Gateway ---

@app.route('/api/<collection_name>', methods=['GET', 'POST'])
@require_client_id
def api_collection(collection_name):
    db = get_db()
    collection = db[collection_name]
    client_id = g.client_id

    if request.method == 'GET':
        # Haal data op van DEZE client
        docs = list(collection.find({'client_id': client_id}))
        log_statistic('GET_LIST', client_id, collection_name)
        return jsonify(format_mongo_doc(docs)), 200

    elif request.method == 'POST':
        data = request.get_json()
        if not data: return jsonify({"error": "No JSON data"}), 400
        
        # Forceer client_id in het document
        data['client_id'] = client_id
        data['created_at'] = datetime.datetime.utcnow()
        
        result = collection.insert_one(data)
        log_statistic('POST', client_id, collection_name)
        
        return jsonify({"message": "Created", "id": str(result.inserted_id)}), 201

@app.route('/api/<collection_name>/<doc_id>', methods=['GET', 'PUT', 'DELETE'])
@require_client_id
def api_document(collection_name, doc_id):
    db = get_db()
    collection = db[collection_name]
    client_id = g.client_id

    try: query_id = ObjectId(doc_id)
    except: query_id = doc_id

    # Query dwingt altijd client_id match af
    query = {'_id': query_id, 'client_id': client_id}

    if request.method == 'GET':
        doc = collection.find_one(query)
        if not doc: return jsonify({"error": "Not found"}), 404
        log_statistic('GET_ONE', client_id, collection_name)
        return jsonify(format_mongo_doc(doc)), 200

    elif request.method == 'PUT':
        data = request.get_json()
        data.pop('_id', None)
        data.pop('client_id', None) # Mag eigenaar niet wijzigen
        data['updated_at'] = datetime.datetime.utcnow()

        res = collection.update_one(query, {'$set': data})
        if res.matched_count == 0: return jsonify({"error": "Not found"}), 404
        log_statistic('PUT', client_id, collection_name)
        return jsonify({"message": "Updated"}), 200

    elif request.method == 'DELETE':
        res = collection.delete_one(query)
        if res.deleted_count == 0: return jsonify({"error": "Not found"}), 404
        log_statistic('DELETE', client_id, collection_name)
        return jsonify({"message": "Deleted"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
