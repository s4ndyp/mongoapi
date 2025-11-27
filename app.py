import os
import datetime
import json
import secrets 
import string 
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, abort, session
from flask_cors import CORS 
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from flask_limiter import Limiter 
from flask_limiter.util import get_remote_address 

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
MONGO_CLIENT = None

# --- Helper Functies ---

def generate_random_key(length=20):
    characters = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(characters) for _ in range(length))

def ensure_indexes(db):
    try:
        # Indexen voor de log historie
        db['statistics'].create_index([("timestamp", 1), ("source", 1)], background=True)
        db['app_data'].create_index([("source_app", 1), ("timestamp", -1)], background=True)
        
        # NIEUW: Index voor de actuele status (Live Database)
        # We slaan actieve items op in 'active_state'. 
        # item_id moet uniek zijn per source_app (zodat client A de taken van client B niet overschrijft)
        db['active_state'].create_index([("source_app", 1), ("item_id", 1)], unique=True, name="unique_item_per_app", background=True)

        db['api_keys'].create_index("key", unique=True, background=True)
        
        print("MongoDB Indexen gecontroleerd.")
    except Exception as e:
        print(f"Waarschuwing indexen: {e}")

def get_db_connection(uri=None):
    global MONGO_CLIENT
    target_uri = uri if uri else app.config.get('MONGO_URI')

    if not target_uri:
        return None, "MongoDB URI is niet geconfigureerd."

    if MONGO_CLIENT is None or uri is not None:
        try:
            client = MongoClient(target_uri, serverSelectionTimeoutMS=5000)
            client.admin.command('ping') 
            
            if uri is None:
                MONGO_CLIENT = client
            else: 
                # Test connection only
                return client, None
            
            db = MONGO_CLIENT['api_gateway_db']
            ensure_indexes(db)
            return MONGO_CLIENT, None
        except Exception as e:
            return None, str(e)
            
    try:
        MONGO_CLIENT.admin.command('ping') 
        return MONGO_CLIENT, None
    except Exception as e:
        MONGO_CLIENT = None
        return None, str(e)

# --- Database Key Management ---
def load_api_keys():
    client, error = get_db_connection()
    if not client: return {}
    db = client['api_gateway_db']
    keys = {}
    for doc in db['api_keys'].find({}):
        keys[doc['client_id']] = {'key': doc['key'], 'description': doc['description']}
    return keys

def save_new_api_key(client_id, key, description):
    client, error = get_db_connection()
    if not client: return False, "DB Error"
    try:
        client['api_gateway_db']['api_keys'].insert_one({
            'client_id': client_id, 'key': key, 'description': description, 'created_at': datetime.datetime.utcnow()
        })
        return True, None
    except Exception as e:
        return False, str(e)

def revoke_api_key_db(client_id):
    client, error = get_db_connection()
    if not client: return False
    try:
        client['api_gateway_db']['api_keys'].delete_one({'client_id': client_id})
        return True, None
    except: return False

# --- APP SETUP ---
app = Flask(__name__)
CORS(app) 
app.config['MONGO_URI'] = DEFAULT_MONGO_URI
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key')

def get_client_id():
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        client, _ = get_db_connection()
        if client:
            key_doc = client['api_gateway_db']['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc: return key_doc['client_id']
    return get_remote_address()

limiter = Limiter(key_func=get_client_id, app=app, default_limits=["1000 per day", "200 per hour"], storage_uri="memory://")

# --- Decorator ---
def require_api_key(f):
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS': # Allow CORS preflight without key
            return f(*args, **kwargs)
            
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authenticatie vereist (Bearer token)"}), 401
        
        token = auth_header.split(' ')[1]
        client, _ = get_db_connection()
        client_id = None
        if client:
            key_doc = client['api_gateway_db']['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc: client_id = key_doc['client_id']
        
        if client_id:
            request.client_id = client_id
            return f(*args, **kwargs)
        else:
            return jsonify({"error": "Ongeldige API-sleutel"}), 401
    wrapper.__name__ = f.__name__ 
    return wrapper

# --- ROUTES ---

# ... (HTML Routes zoals dashboard, client_detail, settings blijven hetzelfde, 
# ik kort ze hier in om focus te leggen op de API logica, maar in de file output zit alles) ...

@app.route('/')
def dashboard():
    return render_template_string(BASE_LAYOUT, page='dashboard', page_content=DASHBOARD_CONTENT)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    # Zelfde logica als voorheen voor settings
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'generate_key':
            desc = request.form.get('key_description', 'Client')
            key = generate_random_key(20)
            c_id = desc.lower().replace(' ', '_') + '_' + str(secrets.randbelow(999))
            if save_new_api_key(c_id, key, desc)[0]:
                session['new_key'] = key
                session['new_key_desc'] = desc
        elif action == 'save':
            app.config['MONGO_URI'] = request.form.get('mongo_uri')
            get_db_connection(None) # Reconnect

    api_keys = load_api_keys()
    new_key = session.pop('new_key', None)
    new_key_desc = session.pop('new_key_desc', None)
    
    return render_template_string(BASE_LAYOUT, page='settings', page_content=render_template_string(SETTINGS_CONTENT, current_uri=app.config['MONGO_URI'], api_keys=api_keys, new_key=new_key, new_key_desc=new_key_desc, new_key_id=""))

# --- NIEUWE API LOGICA (GET & POST) ---

@app.route('/api/health', methods=['GET']) 
def health_check():
    client, _ = get_db_connection()
    return jsonify({"status": "running", "mongodb": "ok" if client else "error"})

@app.route('/api/data', methods=['GET', 'POST']) 
@require_api_key 
def handle_data():
    client, error = get_db_connection()
    if not client: return jsonify({"error": "Database error"}), 503
    db = client['api_gateway_db']
    source_app = request.client_id

    # --- NIEUW: GET REQUEST (Data Ophalen) ---
    if request.method == 'GET':
        try:
            # Haal alle actieve items op uit de 'active_state' collectie voor deze client
            cursor = db['active_state'].find({'source_app': source_app})
            
            projects = []
            items = []
            
            for doc in cursor:
                # Verwijder MongoDB interne _id
                if '_id' in doc: del doc['_id']
                if 'source_app' in doc: del doc['source_app']
                if 'item_id' in doc: del doc['item_id']
                
                # De eigenlijke data zit in 'data'
                entity = doc.get('data', {})
                
                # Sorteer in projecten of items
                # We herkennen projecten omdat ze geen 'projectId' hebben of type='project' (afhankelijk van frontend)
                # In index.html sturen we { ... }
                # We moeten kijken naar de structuur.
                # In index.html saveItemOrProject:
                # Project heeft: name, createdAt, id
                # Item heeft: content, type, projectId...
                
                if 'name' in entity and 'type' not in entity: # Waarschijnlijk een project
                     projects.append(entity)
                else:
                     items.append(entity)
            
            return jsonify({
                "status": "success",
                "projects": projects,
                "items": items
            }), 200
            
        except Exception as e:
            return jsonify({"error": f"Ophalen mislukt: {str(e)}"}), 500

    # --- POST REQUEST (Data Opslaan & Loggen) ---
    elif request.method == 'POST':
        try:
            payload = request.json
            if not payload: return jsonify({"error": "No data"}), 400
            
            action = payload.get('action', 'unknown')
            item_id = payload.get('item_id')
            full_data = payload.get('full_data') # Dit is het echte item object
            
            # 1. Altijd loggen naar historie (Zoals eerst)
            db['app_data'].insert_one({
                'timestamp': datetime.datetime.utcnow(),
                'source_app': source_app,
                'payload': payload
            })
            
            # 2. Update de 'Live' Database (active_state)
            if item_id:
                if action.startswith('save_'):
                    # UPSERT: Als bestaat updaten, anders aanmaken
                    db['active_state'].update_one(
                        {'source_app': source_app, 'item_id': item_id},
                        {'$set': {
                            'source_app': source_app, 
                            'item_id': item_id,
                            'data': full_data,
                            'last_updated': datetime.datetime.utcnow()
                        }},
                        upsert=True
                    )
                elif action.startswith('delete_'):
                    # DELETE: Verwijder uit actieve staat
                    db['active_state'].delete_one({'source_app': source_app, 'item_id': item_id})
            
            return jsonify({"status": "success", "action": action}), 201
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# Layouts (verkort voor overzicht, maar functioneel)
BASE_LAYOUT = """<!DOCTYPE html><html lang="nl" data-bs-theme="dark"><head><meta charset="UTF-8"><title>Gateway</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css"><style>body{background:#121212;color:#e0e0e0}.card{background:#1e1e1e;border:1px solid #333}.sidebar{min-height:100vh;background:#191919;border-right:1px solid #333}.nav-link{color:#aaa}.nav-link.active{color:#fff;background:#333}</style></head><body><div class="container-fluid"><div class="row"><nav class="col-md-3 col-lg-2 d-md-block sidebar collapse p-3"><h4 class="text-white">Gateway</h4><ul class="nav flex-column"><li class="nav-item"><a class="nav-link {{ 'active' if page=='dashboard' else '' }}" href="/">Dashboard</a></li><li class="nav-item"><a class="nav-link {{ 'active' if page=='settings' else '' }}" href="/settings">Settings</a></li></ul></nav><main class="col-md-9 ms-sm-auto col-lg-10 px-md-4 py-4">{{ page_content | safe }}</main></div></div></body></html>"""

DASHBOARD_CONTENT = """<h2>Dashboard</h2><p class="text-muted">De server draait en accepteert nu zowel GET (lezen) als POST (schrijven) requests.</p>"""

SETTINGS_CONTENT = """
<h2>Settings</h2>
<div class="row"><div class="col-md-6"><div class="card p-4">
<form method="POST"><label>Mongo URI</label><input name="mongo_uri" class="form-control mb-2" value="{{ current_uri }}"><button name="action" value="save" class="btn btn-primary">Save URI</button></form>
<hr>
<form method="POST"><label>Beschrijving</label><input name="key_description" class="form-control mb-2"><button name="action" value="generate_key" class="btn btn-success">Genereer Key</button></form>
{% if new_key %}<div class="alert alert-success mt-3">Key: <b>{{ new_key }}</b></div>{% endif %}
</div></div>
<div class="col-md-6"><div class="card p-4"><h5>Active Keys</h5><ul>{% for id, k in api_keys.items() %}<li>{{ k.description }} ({{ id }})</li>{% endfor %}</ul></div></div></div>
"""

if __name__ == '__main__':
    get_db_connection()
    app.run(host='0.0.0.0', port=5000, debug=True)
