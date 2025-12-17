import os
import datetime
import json
from functools import wraps
from flask import Flask, request, jsonify, g, Response
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
from bson.json_util import dumps

app = Flask(__name__)
# CORS: Alles toestaan (beveiliging zit op netwerkniveau/proxy)
CORS(app, resources={r"/*": {"origins": "*"}})

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')

def get_db():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        return client['data_store']
    except Exception as e:
        print(f"DB ERROR: {e}")
        return None

# --- AUTH & FORMATTERS ---

def require_client_id(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_id = request.headers.get('x-client-id') or request.args.get('client_id')
        if not client_id:
            return jsonify({"error": "Missing x-client-id header"}), 400
        g.client_id = client_id
        return f(*args, **kwargs)
    return decorated_function

def format_doc(doc):
    """Vertaalt Database container-structuur naar platte Client-structuur."""
    if isinstance(doc, list):
        return [format_doc(d) for d in doc]
    if isinstance(doc, dict):
        new_doc = {}
        for k, v in doc.items():
            if k == '_id':
                new_doc['_id'] = str(v)
            elif k == '_meta':
                new_doc['_client_id'] = v.get('owner')
                if v.get('created_at'):
                    new_doc['_created_at'] = v.get('created_at').isoformat()
                if v.get('updated_at'):
                    new_doc['_updated_at'] = v.get('updated_at').isoformat()
            else:
                new_doc[k] = v
        return new_doc
    return doc

def clean_incoming_data(data):
    """Verwijdert systeemvelden (startend met _) bij import."""
    if not isinstance(data, dict): return data
    return {k: v for k, v in data.items() if not k.startswith('_')}

# --- ADMIN ROUTES (VOOR DASHBOARD) ---

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    """Verzamelt alle statistieken voor het beheerpaneel."""
    db = get_db()
    if not db: return jsonify({'error': 'DB Offline'}), 500

    cols = db.list_collection_names()
    system_cols = ['clients', 'statistics', 'system.indexes']
    endpoint_names = [c for c in cols if c not in system_cols]

    # 1. Endpoint Statistieken
    endpoint_stats = []
    total_records = 0
    
    # 2. Client Statistieken (Aggregatie over alle collecties)
    client_usage = {} # {client_id: count}

    for col_name in endpoint_names:
        count = db[col_name].count_documents({})
        total_records += count
        endpoint_stats.append({
            'name': col_name,
            'count': count
        })

        # Tel per gebruiker (dit kan zwaar zijn bij miljoenen records, maar prima voor beheer)
        pipeline = [
            {"$group": {"_id": "$_meta.owner", "count": {"$sum": 1}}}
        ]
        results = list(db[col_name].aggregate(pipeline))
        for res in results:
            c_id = res['_id'] or "onbekend"
            client_usage[c_id] = client_usage.get(c_id, 0) + res['count']

    # Database stats
    db_stats = db.command("dbstats")

    return jsonify({
        'endpoints': endpoint_stats,
        'clients_usage': [{'client_id': k, 'total_records': v} for k, v in client_usage.items()],
        'db_info': {
            'data_size_mb': round(db_stats.get('dataSize', 0) / (1024*1024), 2),
            'total_objects': total_records
        }
    })

@app.route('/api/admin/collections/<name>', methods=['DELETE'])
def admin_delete_collection(name):
    """Verwijdert een volledig endpoint."""
    db = get_db()
    db[name].drop()
    return jsonify({"status": "deleted", "collection": name})

@app.route('/api/admin/rename', methods=['POST'])
def admin_rename_collection():
    """Hernoemt een endpoint."""
    db = get_db()
    data = request.json
    old_name = data.get('old_name')
    new_name = data.get('new_name')
    
    if not old_name or not new_name:
        return jsonify({"error": "Namen ontbreken"}), 400
    
    try:
        db[old_name].rename(new_name)
        return jsonify({"status": "renamed"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/admin/export/<name>', methods=['GET'])
def admin_export_collection(name):
    """
    Exporteert endpoint als JSON.
    Format: Platgeslagen met underscores (Import-ready voor Clients).
    """
    db = get_db()
    docs = list(db[name].find({}))
    # We gebruiken format_doc zodat de output 'schoon' en importeerbaar is
    formatted_docs = format_doc(docs)
    
    # Return als downloadbaar bestand
    return Response(
        json.dumps(formatted_docs, indent=2, default=str),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment;filename={name}_export.json"}
    )

@app.route('/api/admin/peek/<name>', methods=['GET'])
def admin_peek_collection(name):
    """Geeft de eerste 5 records terug voor snelle inspectie."""
    db = get_db()
    docs = list(db[name].find({}).limit(5))
    return jsonify(format_doc(docs))

# --- CLIENT API ROUTES ---

@app.route('/api/<collection_name>', methods=['GET', 'POST'])
@require_client_id
def api_collection(collection_name):
    db = get_db()
    col = db[collection_name]
    
    if request.method == 'GET':
        docs = list(col.find({'_meta.owner': g.client_id}))
        return jsonify(format_doc(docs)), 200

    if request.method == 'POST':
        raw_data = request.get_json(silent=True) or {}
        user_data = clean_incoming_data(raw_data)
        
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
    col = db[collection_name]
    
    try: q_id = ObjectId(doc_id)
    except: q_id = doc_id
    
    query = {'_id': q_id, '_meta.owner': g.client_id}

    if request.method == 'GET':
        doc = col.find_one(query)
        return (jsonify(format_doc(doc)), 200) if doc else (jsonify({"error": "Not found"}), 404)

    if request.method == 'PUT':
        user_data = clean_incoming_data(request.get_json(silent=True) or {})
        res = col.update_one(query, {
            '$set': user_data,
            '$set': {'_meta.updated_at': datetime.datetime.utcnow()}
        })
        return jsonify({"status": "updated" if res.matched_count else "not found"}), 200

    if request.method == 'DELETE':
        res = col.delete_one(query)
        return jsonify({"status": "deleted" if res.deleted_count else "not found"}), 200

# --- STATIC DASHBOARD ---
@app.route('/dashboard.html')
@app.route('/')
def dashboard_html():
    return app.send_static_file('dashboard.html') if os.path.exists('static/dashboard.html') else "Dashboard file not found (save code to dashboard.html in same folder)"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
