import os
import datetime
import json
import secrets
import string
import re
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, session
from flask_cors import CORS 
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, CollectionInvalid
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
MONGO_CLIENT = None

# --- Helper Functies ---

def generate_random_key(length=20):
    characters = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(characters) for _ in range(length))

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
                return client, None
            
            # Zorg voor basis indexen
            db = MONGO_CLIENT['api_gateway_db']
            db['api_keys'].create_index("key", unique=True, background=True)
            db['endpoints'].create_index("name", unique=True, background=True) # NIEUW: Endpoint configuratie
            
            return MONGO_CLIENT, None
        except Exception as e:
            MONGO_CLIENT = None
            return None, str(e)
            
    try:
        MONGO_CLIENT.admin.command('ping')
        return MONGO_CLIENT, None
    except Exception as e:
        MONGO_CLIENT = None
        return None, str(e)

def format_size(size_bytes):
    """Zet bytes om naar leesbare KB/MB string."""
    if size_bytes == 0:
        return "0 KB"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(0)
    p = 1024
    while size_bytes >= p and i < len(size_name) - 1:
        size_bytes /= p
        i += 1
    return f"{size_bytes:.2f} {size_name[i]}"

# --- Data Management Functies ---

def get_configured_endpoints():
    """Haalt lijst met dynamische endpoints op."""
    client, _ = get_db_connection()
    if not client: return []
    
    db = client['api_gateway_db']
    return list(db['endpoints'].find({}, {'_id': 0}).sort('name', 1))

def get_endpoint_stats(endpoint_name):
    """Haalt storage statistieken op voor een specifiek endpoint."""
    client, _ = get_db_connection()
    if not client: return {'count': 0, 'size': '0 KB'}
    
    db = client['api_gateway_db']
    coll_name = f"data_{endpoint_name}"
    
    try:
        # Haal low-level collectie statistieken op
        stats = db.command("collstats", coll_name)
        return {
            'count': stats.get('count', 0),
            'size': format_size(stats.get('storageSize', 0)),
            'avgObjSize': format_size(stats.get('avgObjSize', 0))
        }
    except OperationFailure:
        # Collectie bestaat waarschijnlijk nog niet
        return {'count': 0, 'size': '0 KB', 'avgObjSize': '0 B'}

def create_endpoint(name, description):
    """Maakt een nieuw endpoint aan."""
    # Validatie: alleen letters, cijfers en underscores
    if not re.match("^[a-zA-Z0-9_]+$", name):
        return False, "Naam mag alleen letters, cijfers en underscores bevatten."
    
    client, _ = get_db_connection()
    if not client: return False, "Geen database verbinding"
    
    db = client['api_gateway_db']
    try:
        db['endpoints'].insert_one({
            'name': name,
            'description': description,
            'created_at': datetime.datetime.utcnow()
        })
        # Maak alvast de collectie aan (optioneel, maar netjes)
        db.create_collection(f"data_{name}")
        return True, None
    except Exception as e:
        return False, str(e)

def delete_endpoint(name):
    """Verwijdert configuratie EN data van een endpoint."""
    client, _ = get_db_connection()
    if not client: return False
    
    db = client['api_gateway_db']
    try:
        # Verwijder config
        db['endpoints'].delete_one({'name': name})
        # Verwijder data collectie
        db[f"data_{name}"].drop()
        return True
    except Exception:
        return False

# --- API Key Management (Bestaand) ---
def load_api_keys():
    client, _ = get_db_connection()
    if not client: return {}
    db = client['api_gateway_db']
    keys = {}
    for doc in db['api_keys'].find({}):
        keys[doc['client_id']] = {'key': doc['key'], 'description': doc['description']}
    return keys

def save_new_api_key(client_id, key, description):
    client, _ = get_db_connection()
    if not client: return False, "DB Error"
    db = client['api_gateway_db']
    try:
        db['api_keys'].insert_one({'client_id': client_id, 'key': key, 'description': description})
        return True, None
    except Exception as e: return False, str(e)

def revoke_api_key_db(client_id):
    client, _ = get_db_connection()
    if not client: return False, "DB Error"
    db = client['api_gateway_db']
    db['api_keys'].delete_one({'client_id': client_id})
    return True, None

# --- INITIALISATIE ---
app = Flask(__name__)
CORS(app) 
app.config['MONGO_URI'] = DEFAULT_MONGO_URI 

def get_client_id():
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        client, _ = get_db_connection()
        if client:
            db = client['api_gateway_db']
            key_doc = db['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc: return key_doc['client_id']
    return get_remote_address()

limiter = Limiter(key_func=get_client_id, app=app, default_limits=["2000 per day", "500 per hour"], storage_uri="memory://")
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key')

def require_api_key(f):
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS': return jsonify({'status': 'ok'}), 200
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Unauthorized"}), 401
        token = auth_header.split(' ')[1]
        client, _ = get_db_connection()
        client_id = None
        if client:
            db = client['api_gateway_db']
            key_doc = db['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc: client_id = key_doc['client_id']
        
        if client_id:
            request.client_id = client_id
            return f(*args, **kwargs)
        else:
            return jsonify({"error": "Invalid Key"}), 401
    wrapper.__name__ = f.__name__ 
    return wrapper

# --- HTML TEMPLATES ---

BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="nl" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gateway Beheer</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #121212; color: #e0e0e0; }
        .card { background-color: #1e1e1e; border: 1px solid #333; margin-bottom: 20px; }
        .sidebar { min-height: 100vh; background-color: #191919; border-right: 1px solid #333; }
        .nav-link { color: #aaa; }
        .nav-link:hover, .nav-link.active { color: #fff; background-color: #333; border-radius: 5px; }
        .status-dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .dot-green { background-color: #28a745; box-shadow: 0 0 5px #28a745; }
        .dot-red { background-color: #dc3545; box-shadow: 0 0 5px #dc3545; }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            <nav class="col-md-3 col-lg-2 d-md-block sidebar collapse p-3">
                <h4 class="mb-4 text-white"><i class="bi bi-hdd-network"></i> Gateway</h4>
                <ul class="nav flex-column">
                    <li class="nav-item"><a class="nav-link {{ 'active' if page == 'dashboard' else '' }}" href="/"><i class="bi bi-speedometer2"></i> Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link {{ 'active' if page == 'endpoints' else '' }}" href="/endpoints"><i class="bi bi-diagram-3"></i> Endpoints</a></li>
                    <li class="nav-item"><a class="nav-link {{ 'active' if page == 'settings' else '' }}" href="/settings"><i class="bi bi-gear"></i> Instellingen</a></li>
                </ul>
            </nav>
            <main class="col-md-9 ms-sm-auto col-lg-10 px-md-4 py-4">
                {% with messages = get_flashed_messages(with_categories=true) %}
                  {% if messages %}
                    {% for category, message in messages %}
                      <div class="alert alert-{{ category }} alert-dismissible fade show">{{ message }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
                    {% endfor %}
                  {% endif %}
                {% endwith %}
                {{ page_content | safe }}
            </main>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

DASHBOARD_CONTENT = """
    <h2 class="mb-4">Dashboard</h2>
    <div class="row mb-4">
        <div class="col-md-4">
            <div class="card p-3">
                <h5 class="text-muted">MongoDB Status</h5>
                <div class="d-flex align-items-center mt-2">
                    {% if db_connected %}
                        <span class="status-dot dot-green"></span> <h4 class="m-0">Verbonden</h4>
                    {% else %}
                        <span class="status-dot dot-red"></span> <h4 class="m-0">Fout</h4>
                    {% endif %}
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card p-3">
                <h5 class="text-muted">Actieve Endpoints</h5>
                <h3 class="mt-2">{{ endpoint_count }}</h3>
            </div>
        </div>
         <div class="col-md-4">
            <div class="card p-3 border-info">
                <h5 class="text-info">Totale Opslag</h5>
                <h3 class="mt-2">{{ total_storage }}</h3>
            </div>
        </div>
    </div>
"""

ENDPOINTS_CONTENT = """
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2>Endpoints Beheer</h2>
        <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addEndpointModal">
            <i class="bi bi-plus-lg"></i> Nieuw Endpoint
        </button>
    </div>

    <div class="row">
        {% for ep in endpoints %}
        <div class="col-md-6 col-xl-4">
            <div class="card h-100">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="m-0 font-monospace text-info">/api/{{ ep.name }}</h5>
                    <form method="POST" action="/endpoints/delete" onsubmit="return confirm('Dit verwijdert ook alle data in dit endpoint. Zeker weten?');">
                        <input type="hidden" name="name" value="{{ ep.name }}">
                        <button type="submit" class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button>
                    </form>
                </div>
                <div class="card-body">
                    <p class="text-muted small">{{ ep.description }}</p>
                    <hr class="border-secondary">
                    <div class="row text-center">
                        <div class="col-6 border-end border-secondary">
                            <small class="text-muted d-block">Items</small>
                            <span class="fs-5">{{ ep.stats.count }}</span>
                        </div>
                        <div class="col-6">
                            <small class="text-muted d-block">Opslag</small>
                            <span class="fs-5 text-warning">{{ ep.stats.size }}</span>
                        </div>
                    </div>
                </div>
                <div class="card-footer bg-dark">
                    <small class="text-muted">Curl: <code>POST /api/{{ ep.name }}</code></small>
                </div>
            </div>
        </div>
        {% else %}
        <div class="col-12 text-center text-muted py-5">
            <h4>Geen endpoints geconfigureerd.</h4>
            <p>Klik op 'Nieuw Endpoint' om te beginnen.</p>
        </div>
        {% endfor %}
    </div>

    <!-- Modal -->
    <div class="modal fade" id="addEndpointModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content bg-dark text-white border-secondary">
                <div class="modal-header border-secondary">
                    <h5 class="modal-title">Nieuw Endpoint Toevoegen</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <form method="POST" action="/endpoints">
                    <div class="modal-body">
                        <div class="mb-3">
                            <label class="form-label">Endpoint Naam (in URL)</label>
                            <div class="input-group">
                                <span class="input-group-text bg-secondary text-white border-secondary">/api/</span>
                                <input type="text" name="name" class="form-control bg-black text-white border-secondary" placeholder="products" required pattern="[a-zA-Z0-9_]+">
                            </div>
                            <small class="text-muted">Alleen letters, cijfers en underscores.</small>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Omschrijving</label>
                            <input type="text" name="description" class="form-control bg-black text-white border-secondary" placeholder="Opslag voor productcatalogus">
                        </div>
                    </div>
                    <div class="modal-footer border-secondary">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annuleren</button>
                        <button type="submit" class="btn btn-primary">Aanmaken</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
"""

SETTINGS_CONTENT = """
    <h2>Instellingen</h2>
    <div class="row mt-4">
        <div class="col-md-6">
            <div class="card p-4">
                <h5>API Sleutel Genereren</h5>
                <form method="POST" action="/settings">
                    <div class="mb-3">
                        <input type="text" name="key_description" class="form-control bg-dark text-white" placeholder="Naam (bv. App V2)" required>
                    </div>
                    <button type="submit" name="action" value="generate_key" class="btn btn-success">Genereer Sleutel</button>
                </form>
                {% if new_key %}
                <div class="alert alert-success mt-3">
                    <strong>Nieuwe Key:</strong> <code class="user-select-all">{{ new_key }}</code>
                </div>
                {% endif %}
            </div>
        </div>
        <div class="col-md-6">
            <div class="card p-4">
                <h5>Actieve Sleutels</h5>
                <ul class="list-group list-group-flush">
                    {% for id, data in api_keys.items() %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between">
                        <span>{{ data.description }} <small class="text-muted">({{ id }})</small></span>
                        <form method="POST" action="/settings" onsubmit="return confirm('Intrekken?');">
                            <input type="hidden" name="action" value="revoke_key">
                            <input type="hidden" name="client_id" value="{{ id }}">
                            <button class="btn btn-sm btn-danger">X</button>
                        </form>
                    </li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>
"""

# --- ROUTES ---

@app.route('/')
def dashboard():
    client, _ = get_db_connection()
    db_connected = client is not None
    endpoint_count = 0
    total_size_bytes = 0
    
    if db_connected:
        endpoints = get_configured_endpoints()
        endpoint_count = len(endpoints)
        for ep in endpoints:
            try:
                stats = client['api_gateway_db'].command("collstats", f"data_{ep['name']}")
                total_size_bytes += stats.get('storageSize', 0)
            except: pass
            
    return render_template_string(BASE_LAYOUT, page='dashboard', 
        page_content=render_template_string(DASHBOARD_CONTENT, 
            db_connected=db_connected, 
            endpoint_count=endpoint_count,
            total_storage=format_size(total_size_bytes)
        ))

@app.route('/endpoints', methods=['GET', 'POST'])
def endpoints_page():
    if request.method == 'POST':
        name = request.form.get('name')
        desc = request.form.get('description')
        success, err = create_endpoint(name, desc)
        if success: flash(f"Endpoint '{name}' aangemaakt.", "success")
        else: flash(f"Fout: {err}", "danger")
        return redirect(url_for('endpoints_page'))

    endpoints = get_configured_endpoints()
    # Verrijk endpoints met statistieken
    for ep in endpoints:
        ep['stats'] = get_endpoint_stats(ep['name'])

    content = render_template_string(ENDPOINTS_CONTENT, endpoints=endpoints)
    return render_template_string(BASE_LAYOUT, page='endpoints', page_content=content)

@app.route('/endpoints/delete', methods=['POST'])
def delete_endpoint_route():
    name = request.form.get('name')
    if delete_endpoint(name):
        flash(f"Endpoint '{name}' verwijderd.", "warning")
    else:
        flash("Kon endpoint niet verwijderen.", "danger")
    return redirect(url_for('endpoints_page'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'generate_key':
            desc = request.form.get('key_description')
            key = generate_random_key()
            client_id = desc.lower().replace(" ", "_") + "_" + secrets.token_hex(2)
            if save_new_api_key(client_id, key, desc)[0]:
                session['new_key'] = key
                flash("Sleutel aangemaakt", "success")
        elif action == 'revoke_key':
            revoke_api_key_db(request.form.get('client_id'))
            flash("Sleutel ingetrokken", "warning")
        return redirect(url_for('settings'))

    new_key = session.pop('new_key', None)
    content = render_template_string(SETTINGS_CONTENT, api_keys=load_api_keys(), new_key=new_key)
    return render_template_string(BASE_LAYOUT, page='settings', page_content=content)

@app.route('/api/health')
def health():
    client, _ = get_db_connection()
    return jsonify({"status": "running", "db": "ok" if client else "error"})

# --- DYNAMIC REST API GATEWAY ---

@app.route('/api/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
@require_api_key
@limiter.limit("1000 per hour")
def handle_dynamic_endpoint(endpoint_name):
    """
    Dynamische handler voor ALLE geconfigureerde endpoints.
    GET: Haal data op (optioneel filteren via query params)
    POST: Voeg data toe
    DELETE: Verwijder data (via query param ?id=...)
    """
    client, _ = get_db_connection()
    if not client: return jsonify({"error": "DB failure"}), 503
    db = client['api_gateway_db']
    
    # 1. Controleer of endpoint bestaat
    if not db['endpoints'].find_one({'name': endpoint_name}):
        return jsonify({"error": f"Endpoint '{endpoint_name}' not found"}), 404

    collection = db[f"data_{endpoint_name}"]

    # 2. Handle POST (Create)
    if request.method == 'POST':
        data = request.json
        if not data: return jsonify({"error": "No JSON body"}), 400
        
        # Voeg metadata toe
        doc = {
            "data": data,
            "meta": {
                "created_at": datetime.datetime.utcnow(),
                "client_id": getattr(request, 'client_id', 'unknown'),
                "ip": get_remote_address()
            }
        }
        result = collection.insert_one(doc)
        return jsonify({"status": "created", "id": str(result.inserted_id)}), 201

    # 3. Handle GET (Read)
    elif request.method == 'GET':
        # Simpele filtering: ?status=active -> zoekt naar {"data.status": "active"}
        query = {}
        for k, v in request.args.items():
            query[f"data.{k}"] = v
            
        limit = int(request.args.get('_limit', 50))
        cursor = collection.find(query, {'_id': 0}).sort("meta.created_at", -1).limit(limit)
        return jsonify(list(cursor)), 200

    # 4. Handle DELETE
    elif request.method == 'DELETE':
        # Vereist ?id=... of ?filter_field=value
        # Voor veiligheid nu even alleen 'delete all' als specifieke header aanwezig is, of custom logica
        # Dit is een voorbeeld, wees voorzichtig met DELETE in productie
        return jsonify({"error": "DELETE not implemented for safety"}), 501

if __name__ == '__main__':
    get_db_connection()
    app.run(host='0.0.0.0', port=5000, debug=True)
