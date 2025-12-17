import os
import datetime
from functools import wraps
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId

app = Flask(__name__)
# CORS staat alles toe voor maximale flexibiliteit achter je proxy
CORS(app, resources={r"/*": {"origins": "*"}})

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')

def get_db():
    try:
        # Gebruik serverSelectionTimeout zodat de app niet bevriest als DB offline is
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        return client['data_store']
    except:
        return None

def require_client_id(f):
    """Decorator die alleen checkt op client_id (Trusted Proxy mode)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_id = request.headers.get('x-client-id') or request.args.get('client_id')
        if not client_id:
            return jsonify({"error": "Missing x-client-id header"}), 400
        g.client_id = client_id
        return f(*args, **kwargs)
    return decorated_function

def format_doc(doc):
    """
    Vertaalt DB naar Client:
    - Verplaatst velden uit _meta naar de root met een underscore.
    - Behoudt de rest van de data plat.
    """
    if isinstance(doc, list):
        return [format_doc(d) for d in doc]
    if isinstance(doc, dict):
        new_doc = {}
        for k, v in doc.items():
            if k == '_id':
                new_doc['_id'] = str(v)
            elif k == '_meta':
                # Systeemvelden plat slaan met een underscore
                new_doc['_client_id'] = v.get('owner')
                if v.get('created_at'):
                    new_doc['_created_at'] = v.get('created_at').isoformat()
                if v.get('updated_at'):
                    new_doc['_updated_at'] = v.get('updated_at').isoformat()
            else:
                # Gebruikersdata (kan ook eigen 'created_at' bevatten zonder conflict!)
                new_doc[k] = v
        return new_doc
    return doc

def clean_incoming_data(data):
    """
    Verwijdert alle velden die met een _ beginnen uit de input van de client.
    Dit voorkomt dat een client systeemvelden zoals _client_id kan vervalsen.
    """
    if not isinstance(data, dict): return data
    # Verwijder alle keys die beginnen met _ (behalve eventueel geneste data)
    return {k: v for k, v in data.items() if not k.startswith('_')}

# --- API ROUTES ---

@app.route('/api/<collection_name>', methods=['GET', 'POST'])
@require_client_id
def api_collection(collection_name):
    db = get_db()
    if db is None: return jsonify({"error": "Database Offline"}), 503
    col = db[collection_name]
    
    if request.method == 'GET':
        # Filteren op de interne container
        docs = list(col.find({'_meta.owner': g.client_id}))
        return jsonify(format_doc(docs)), 200

    if request.method == 'POST':
        raw_data = request.get_json(silent=True) or {}
        
        # 1. Verwijder alle underscore-velden die de client meestuurt (de 'platgeslagen' export data)
        user_data = clean_incoming_data(raw_data)
        
        # 2. Voeg de verse systeem-container toe
        user_data['_meta'] = {
            'owner': g.client_id,
            'created_at': datetime.datetime.utcnow()
        }
        
        result = col.insert_one(user_data)
        return jsonify({"_id": str(result.inserted_id), "status": "created"}), 201

@app.route('/api/<collection_name>/<doc_id>', methods=['GET', 'PUT', 'DELETE'])
@require_client_id
def api_document(collection_name, doc_id):
    db = get_db()
    if db is None: return jsonify({"error": "Database Offline"}), 503
    col = db[collection_name]
    
    try: q_id = ObjectId(doc_id)
    except: q_id = doc_id
    
    query = {'_id': q_id, '_meta.owner': g.client_id}

    if request.method == 'GET':
        doc = col.find_one(query)
        return (jsonify(format_doc(doc)), 200) if doc else (jsonify({"error": "Not found"}), 404)

    if request.method == 'PUT':
        raw_data = request.get_json(silent=True) or {}
        user_data = clean_incoming_data(raw_data)
        
        # Behoud bestaande meta, maar voeg updated_at toe
        res = col.update_one(query, {
            '$set': user_data,
            '$set': {'_meta.updated_at': datetime.datetime.utcnow()}
        })
        return jsonify({"status": "updated" if res.matched_count else "not found"}), 200

    if request.method == 'DELETE':
        res = col.delete_one(query)
        return jsonify({"status": "deleted" if res.deleted_count else "not found"}), 200

# --- DASHBOARD DATA ---

@app.route('/dashboard_data')
def dashboard_data():
    db = get_db()
    if db is None: return jsonify({'error': 'DB Offline'}), 500
    
    cols = db.list_collection_names()
    endpoints = [c for c in cols if c not in ['clients', 'statistics', 'system.indexes']]
    
    # We laten de clients collectie even voor wat het is als simpel adresboek
    clients = list(db.clients.find({}, {'description': 1, '_id': 1}))

    return jsonify({
        'stats': { 'active_endpoints': len(endpoints), 'known_clients': len(clients) },
        'clients': format_doc(clients),
        'endpoints': endpoints
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
