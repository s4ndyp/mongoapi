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

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Gebruik 'mongo' als de service in Docker zo heet, anders '127.0.0.1'
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
app.config['MONGO_URI'] = DEFAULT_MONGO_URI

def get_db():
    try:
        client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=2000)
        # We geven het database object terug. 
        # De check of het gelukt is doen we met 'is not None'
        return client['data_store']
    except Exception as e:
        print(f"DATABASE FOUT: {e}")
        return None

def require_client_id(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_id = request.headers.get('x-client-id') or request.args.get('client_id')
        if not client_id:
            return jsonify({"error": "Missing x-client-id header"}), 400
        g.client_id = client_id
        return f(*args, **kwargs)
    return decorated_function

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

# --- API ROUTES ---

@app.route('/api/<collection_name>', methods=['GET', 'POST'])
@require_client_id
def api_collection(collection_name):
    db = get_db()
    # DE FIX: Expliciet vergelijken met None
    if db is None:
        return jsonify({"error": "Database offline"}), 503
        
    collection = db[collection_name]
    client_id = g.client_id

    try:
        if request.method == 'GET':
            docs = list(collection.find({'client_id': client_id}))
            return jsonify(format_mongo_doc(docs)), 200

        elif request.method == 'POST':
            data = request.get_json(silent=True)
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            
            data['client_id'] = client_id
            data['created_at'] = datetime.datetime.utcnow()
            
            result = collection.insert_one(data)
            return jsonify({"id": str(result.inserted_id)}), 201
    except Exception as e:
        print(f"Fout in route: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/dashboard_data')
def dashboard_data():
    db = get_db()
    if db is None: return jsonify({'error': 'DB Offline'}), 500
    
    cols = db.list_collection_names()
    endpoints = [c for c in cols if c not in ['clients', 'statistics']]
    clients = list(db.clients.find({}, {'description': 1, '_id': 1}))

    return jsonify({
        'stats': { 'active_endpoints': len(endpoints), 'known_clients': len(clients) },
        'clients': format_mongo_doc(clients),
        'endpoints': endpoints
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
