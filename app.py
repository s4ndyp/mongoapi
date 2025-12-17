import os
import datetime
import json
import traceback
from functools import wraps
from flask import Flask, request, jsonify, g, Response, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')

def get_db():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        return client['data_store']
    except Exception as e:
        print(f"DB ERROR: {e}")
        return None

# --- SYSTEM HELPERS ---

def get_config(db, col_name):
    """Haalt instellingen op voor een collectie (Lock, TTL)."""
    return db['_g2_config'].find_one({'_id': col_name}) or {}

def log_activity(db, col_name, client_id, is_error=False, error_msg=None):
    """Logt activiteit voor Pulse (6), Client Last Seen (9) en Error Log (10)."""
    now = datetime.datetime.utcnow()
    
    # 1. Update Endpoint Activity (voor Traffic Lights)
    db['_g2_config'].update_one(
        {'_id': col_name}, 
        {'$set': {'last_activity': now}}, 
        upsert=True
    )

    # 2. Update Client Activity
    if client_id:
        db['_g2_config'].update_one(
            {'_id': f"client_{client_id}"},
            {'$set': {'type': 'client_stats', 'last_seen': now, 'client_id': client_id}},
            upsert=True
        )

    # 3. Log Error if needed
    if is_error:
        db['_g2_errors'].insert_one({
            'timestamp': now,
            'endpoint': col_name,
            'client_id': client_id,
            'error': str(error_msg)
        })

def check_lock(f):
    """(12) Endpoint Lock Middleware."""
    @wraps(f)
    def decorated_function(collection_name, *args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE']:
            db = get_db()
            config = get_config(db, collection_name)
            if config.get('locked', False):
                return jsonify({"error": "Endpoint is LOCKED (Read-Only)"}), 403
        return f(collection_name, *args, **kwargs)
    return decorated_function

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
    if isinstance(doc, list): return [format_doc(d) for d in doc]
    if isinstance(doc, dict):
        new_doc = {}
        for k, v in doc.items():
            if k == '_id': new_doc['_id'] = str(v)
            elif k == '_meta':
                new_doc['_client_id'] = v.get('owner')
                if v.get('created_at'): new_doc['_created_at'] = v.get('created_at').isoformat()
                if v.get('updated_at'): new_doc['_updated_at'] = v.get('updated_at').isoformat()
            else: new_doc[k] = v
        return new_doc
    return doc

def clean_incoming_data(data):
    if not isinstance(data, dict): return data
    return {k: v for k, v in data.items() if not k.startswith('_')}

# --- ADMIN ROUTES ---

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    """Verzamelt data voor Dashboard (6, 8, 9, 20)."""
    db = get_db()
    if not db: return jsonify({'error': 'DB Offline'}), 500

    cols = db.list_collection_names()
    ignore = ['clients', 'statistics', 'system.indexes', '_g2_config', '_g2_snapshots', '_g2_errors']
    endpoint_names = [c for c in cols if c not in ignore]

    endpoint_stats = []
    total_records = 0
    client_stats = []

    # Haal configs op (voor locks/last_activity)
    configs = {doc['_id']: doc for doc in db['_g2_config'].find()}

    # Haal DB stats op voor (8) Heatmap
    db_stats = db.command("dbstats")
    max_size = 1 # avoid div by zero
    
    # Pre-calc sizes
    col_sizes = {}
    for c in endpoint_names:
        s = db.command("collstats", c)['size']
        col_sizes[c] = s
        if s > max_size: max_size = s

    for col_name in endpoint_names:
        count = db[col_name].count_documents({})
        total_records += count
        
        conf = configs.get(col_name, {})
        last_act = conf.get('last_activity')
        
        endpoint_stats.append({
            'name': col_name, 
            'count': count,
            'owners': db[col_name].distinct('_meta.owner'),
            'size_pct': (col_sizes[col_name] / max_size) * 100, # (8) Heatmap
            'last_activity': last_act.isoformat() if last_act else None, # (6, 20) Pulse
            'locked': conf.get('locked', False), # (12) Lock status
            'ttl': conf.get('ttl_days', 0) # (11) TTL
        })

    # (9) Client Last Seen
    client_config_docs = db['_g2_config'].find({'type': 'client_stats'})
    c_last_seen_map = {d['client_id']: d.get('last_seen') for d in client_config_docs}

    # Clients usage aggregatie
    usage_map = {}
    for col_name in endpoint_names:
        pipeline = [{"$group": {"_id": "$_meta.owner", "count": {"$sum": 1}}}]
        for res in db[col_name].aggregate(pipeline):
            c_id = res['_id'] or "onbekend"
            usage_map[c_id] = usage_map.get(c_id, 0) + res['count']
    
    for cid, count in usage_map.items():
        ls = c_last_seen_map.get(cid)
        client_stats.append({
            'client_id': cid,
            'total_records': count,
            'last_seen': ls.isoformat() if ls else None
        })

    # (10) Errors (Laatste 10)
    errors = list(db['_g2_errors'].find().sort('timestamp', -1).limit(10))
    formatted_errors = [{
        'time': e['timestamp'].isoformat(),
        'ep': e['endpoint'],
        'msg': e['error']
    } for e in errors]

    return jsonify({
        'endpoints': endpoint_stats,
        'clients': client_stats,
        'errors': formatted_errors,
        'db_info': {
            'data_size_mb': round(db_stats.get('dataSize', 0) / (1024*1024), 2),
            'total_objects': total_records
        }
    })

@app.route('/api/admin/search', methods=['POST'])
def admin_search():
    """(3) Deep Search."""
    db = get_db()
    data = request.json
    col = data.get('collection')
    term = data.get('term')
    
    # Zoek in alle tekstvelden (regex) of op ID
    query = {}
    if term:
        try:
            query = {"$or": [
                {"_id": ObjectId(term)},
                {"_meta.owner": {"$regex": term, "$options": "i"}}
            ]}
        except:
            # Als term geen ObjectId is, zoek in values
            # Dit is een simpele implementatie, voor diepe search op alle velden is een text index beter
            query = {"$where": f"JSON.stringify(this).indexOf('{term}') != -1"}

    docs = list(db[col].find(query).limit(50))
    return jsonify(format_doc(docs))

@app.route('/api/admin/bulk_delete', methods=['POST'])
def admin_bulk_delete():
    """(4) Bulk Actions."""
    db = get_db()
    data = request.json
    col = data.get('collection')
    ids = data.get('ids', [])
    
    obj_ids = [ObjectId(i) for i in ids]
    res = db[col].delete_many({'_id': {'$in': obj_ids}})
    return jsonify({"deleted": res.deleted_count})

@app.route('/api/admin/clone', methods=['POST'])
def admin_clone():
    """(5) Endpoint Clone."""
    db = get_db()
    data = request.json
    src = data.get('source')
    dest = data.get('destination')
    
    pipeline = [{"$match": {}}, {"$out": dest}]
    db[src].aggregate(pipeline)
    return jsonify({"status": "cloned"})

@app.route('/api/admin/settings', methods=['POST'])
def admin_settings():
    """(11, 12) Update Lock & TTL."""
    db = get_db()
    data = request.json
    col = data.get('collection')
    
    update = {}
    if 'locked' in data: update['locked'] = data['locked']
    if 'ttl_days' in data: update['ttl_days'] = int(data['ttl_days'])
    
    db['_g2_config'].update_one({'_id': col}, {'$set': update}, upsert=True)
    return jsonify({"status": "updated"})

@app.route('/api/admin/cleanup', methods=['POST'])
def admin_cleanup():
    """(11) Voert TTL opschoning uit."""
    db = get_db()
    configs = db['_g2_config'].find({'ttl_days': {'$gt': 0}})
    report = []
    
    for conf in configs:
        days = conf['ttl_days']
        col_name = conf['_id']
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        
        # Verwijder op basis van created_at
        res = db[col_name].delete_many({'_meta.created_at': {'$lt': cutoff}})
        if res.deleted_count > 0:
            report.append(f"{col_name}: {res.deleted_count} items verwijderd (> {days} dagen).")
            
    return jsonify({"report": report})

@app.route('/api/admin/snapshot', methods=['POST'])
def admin_snapshot():
    """(14) Maak Snapshot."""
    db = get_db()
    data = request.json
    col = data.get('collection')
    snap_name = f"{col}_snap_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Kopieer naar snapshot collectie
    pipeline = [{"$match": {}}, {"$out": snap_name}]
    db[col].aggregate(pipeline)
    
    # Log in snapshots lijst
    db['_g2_snapshots'].insert_one({
        'original': col,
        'snapshot_name': snap_name,
        'created_at': datetime.datetime.utcnow()
    })
    return jsonify({"status": "created", "snapshot": snap_name})

@app.route('/api/admin/record/<col_name>/<doc_id>', methods=['PUT'])
def admin_update_record(col_name, doc_id):
    """(1) JSON Editor Save."""
    db = get_db()
    try:
        # Hier accepteren we ruwe updates van de admin editor
        # We halen het binnenkomende object uit elkaar om meta te beschermen indien nodig
        # Maar als ADMIN mag je eigenlijk alles aanpassen.
        # Voor veiligheid: we respecteren de container structuur
        new_doc = request.json
        
        # Vertaal terug van plat (client view) naar container (db view)
        # 1. Haal _meta velden eruit
        meta = {
            'owner': new_doc.get('_client_id'),
            'created_at': datetime.datetime.fromisoformat(new_doc.get('_created_at')) if new_doc.get('_created_at') else None,
            'updated_at': datetime.datetime.utcnow()
        }
        
        # 2. Schoon data op (verwijder _ velden)
        data = clean_incoming_data(new_doc)
        data['_meta'] = meta
        
        db[col_name].replace_one({'_id': ObjectId(doc_id)}, data)
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Bestaande admin routes (rename, delete, export...) blijven hieronder...
# [IK HEB DEZE INGEKORT VOOR LEESBAARHEID, ZE ZIJN HETZELFDE ALS VOORHEEN]
@app.route('/api/admin/rename', methods=['POST'])
def admin_rename():
    db = get_db()
    d = request.json
    try: db[d['old_name']].rename(d['new_name']); return jsonify({"status":"ok"})
    except Exception as e: return jsonify({"error":str(e)}),400

@app.route('/api/admin/collections/<name>', methods=['DELETE'])
def admin_del_col(name):
    get_db()[name].drop(); return jsonify({"status":"deleted"})

@app.route('/api/admin/export/<name>', methods=['GET'])
def admin_exp(name):
    d = list(get_db()[name].find({})); return Response(json.dumps(format_doc(d), default=str), mimetype="application/json", headers={"Content-Disposition":f"attachment;filename={name}.json"})

# --- GATEWAY ROUTES (Met Logging & Locking) ---

@app.route('/api/<collection_name>', methods=['GET', 'POST'])
@require_client_id
@check_lock # (12)
def api_collection(collection_name):
    db = get_db()
    if not db: return jsonify({"error": "DB Offline"}), 503
    
    try:
        if request.method == 'GET':
            log_activity(db, collection_name, g.client_id)
            docs = list(db[collection_name].find({'_meta.owner': g.client_id}))
            return jsonify(format_doc(docs)), 200

        if request.method == 'POST':
            log_activity(db, collection_name, g.client_id)
            raw_data = request.get_json(silent=True) or {}
            user_data = clean_incoming_data(raw_data)
            user_data['_meta'] = {'owner': g.client_id, 'created_at': datetime.datetime.utcnow()}
            result = db[collection_name].insert_one(user_data)
            return jsonify({"_id": str(result.inserted_id), "status": "created"}), 201
            
    except Exception as e:
        log_activity(db, collection_name, g.client_id, is_error=True, error_msg=e)
        return jsonify({"error": "Server Error"}), 500

@app.route('/api/<collection_name>/<doc_id>', methods=['GET', 'PUT', 'DELETE'])
@require_client_id
@check_lock # (12)
def api_document(collection_name, doc_id):
    db = get_db()
    if not db: return jsonify({"error": "DB Offline"}), 503
    
    try:
        try: q_id = ObjectId(doc_id)
        except: q_id = doc_id
        query = {'_id': q_id, '_meta.owner': g.client_id}
        col = db[collection_name]

        if request.method == 'GET':
            log_activity(db, collection_name, g.client_id)
            doc = col.find_one(query)
            return (jsonify(format_doc(doc)), 200) if doc else (jsonify({"error": "Not found"}), 404)

        if request.method == 'PUT':
            log_activity(db, collection_name, g.client_id)
            user_data = clean_incoming_data(request.get_json(silent=True) or {})
            res = col.update_one(query, {'$set': user_data, '$set': {'_meta.updated_at': datetime.datetime.utcnow()}})
            return jsonify({"status": "updated" if res.matched_count else "not found"}), 200

        if request.method == 'DELETE':
            log_activity(db, collection_name, g.client_id)
            res = col.delete_one(query)
            return jsonify({"status": "deleted" if res.deleted_count else "not found"}), 200

    except Exception as e:
        log_activity(db, collection_name, g.client_id, is_error=True, error_msg=e)
        return jsonify({"error": "Server Error"}), 500

@app.route('/dashboard.html')
@app.route('/')
def dashboard_html():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(root_dir, 'dashboard.html')):
        return send_from_directory(root_dir, 'dashboard.html')
    return "Dashboard HTML niet gevonden."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
