import os
import datetime
import json
import secrets
import string
import re
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, session
from flask_cors import CORS 
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from bson import ObjectId

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
MONGO_CLIENT = None
app = Flask(__name__)
CORS(app) 
app.config['MONGO_URI'] = DEFAULT_MONGO_URI 
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-this')

# --- Helper: Random Key ---
def generate_random_key(length=20):
    characters = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(characters) for _ in range(length))

# --- Helper: Opslag Formatteren (KB/MB) ---
def format_size(size_bytes):
    if size_bytes == 0: return "0 KB"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(0)
    p = 1024
    while size_bytes >= p and i < len(size_name) - 1:
        size_bytes /= p
        i += 1
    return f"{size_bytes:.2f} {size_name[i]}"

# --- Database Connectie & Indexen ---
def ensure_indexes(db):
    try:
        # Index voor statistieken (grafieken en client details)
        db['statistics'].create_index([("timestamp", 1), ("source", 1)], background=True)
        # TTL Index: verwijder stats na 1 jaar
        db['statistics'].create_index("timestamp", expireAfterSeconds=31536000, background=True) 
        
        # Indexen voor API Keys
        db['api_keys'].create_index("key", unique=True, background=True)
        db['api_keys'].create_index("client_id", unique=True, background=True)
        
        # NIEUW: Index voor dynamische endpoints configuratie
        db['endpoints'].create_index("name", unique=True, background=True)
        
        print("MongoDB Indexen gecontroleerd.")
    except Exception as e:
        print(f"Waarschuwing indexen: {e}")

def get_db_connection(uri=None):
    global MONGO_CLIENT
    target_uri = uri if uri else app.config.get('MONGO_URI')

    if not target_uri: return None, "URI missing"

    if MONGO_CLIENT is None or uri is not None:
        try:
            client = MongoClient(target_uri, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            if uri is None:
                MONGO_CLIENT = client
                ensure_indexes(MONGO_CLIENT['api_gateway_db'])
            else:
                return client, None
            return MONGO_CLIENT, None
        except Exception as e:
            return None, str(e)
            
    try:
        MONGO_CLIENT.admin.command('ping')
        return MONGO_CLIENT, None
    except Exception as e:
        MONGO_CLIENT = None
        return None, str(e)

# --- Logging voor Statistieken ---
def log_statistic(action, source_app, endpoint="default"):
    client, _ = get_db_connection()
    if client:
        try:
            db = client['api_gateway_db']
            db['statistics'].insert_one({
                'timestamp': datetime.datetime.utcnow(),
                'action': action,
                'source': source_app,
                'endpoint': endpoint
            })
        except Exception as e:
            print(f"Log error: {e}")

# --- Endpoint Management Functies ---
def get_configured_endpoints():
    client, _ = get_db_connection()
    endpoints = []
    
    # 1. Voeg het standaard systeem endpoint toe (Legacy support)
    endpoints.append({
        'name': 'data',
        'description': 'Standaard Endpoint (Legacy / app_data)',
        'system': True,
        'created_at': datetime.datetime.min
    })

    if client:
        # 2. Voeg dynamische endpoints uit DB toe
        try:
            db_endpoints = list(client['api_gateway_db']['endpoints'].find({}, {'_id': 0}).sort('name', 1))
            for ep in db_endpoints:
                if ep.get('name') != 'data':
                    ep['system'] = False
                    endpoints.append(ep)
        except Exception as e:
            print(f"Fout bij ophalen endpoints: {e}")
            
    return endpoints

def get_endpoint_stats(endpoint_name):
    client, _ = get_db_connection()
    if not client: return {'count': 0, 'size': '0 KB'}
    coll_name = 'app_data' if endpoint_name == 'data' else f"data_{endpoint_name}"
    try:
        stats = client['api_gateway_db'].command("collstats", coll_name)
        return {'count': stats.get('count', 0), 'size': format_size(stats.get('storageSize', 0))}
    except:
        return {'count': 0, 'size': '0 KB'}

def create_endpoint(name, description):
    if not re.match("^[a-zA-Z0-9_]+$", name):
        return False, "Naam mag alleen letters, cijfers en underscores bevatten."
    if name == 'data':
        return False, "De naam 'data' is gereserveerd voor het systeem."
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    try:
        client['api_gateway_db']['endpoints'].insert_one({
            'name': name, 'description': description, 'created_at': datetime.datetime.utcnow()
        })
        client['api_gateway_db'].create_collection(f"data_{name}")
        return True, None
    except Exception as e: return False, str(e)

def delete_endpoint(name):
    if name == 'data': return False
    client, _ = get_db_connection()
    if not client: return False
    try:
        client['api_gateway_db']['endpoints'].delete_one({'name': name})
        client['api_gateway_db'][f"data_{name}"].drop()
        return True
    except: return False

# --- API Key Management ---
def load_api_keys():
    client, _ = get_db_connection()
    if not client: return {}
    keys = {}
    for doc in client['api_gateway_db']['api_keys'].find({}):
        keys[doc['client_id']] = {'key': doc['key'], 'description': doc['description']}
    return keys

def save_new_api_key(client_id, key, description):
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    try:
        client['api_gateway_db']['api_keys'].insert_one({
            'client_id': client_id, 'key': key, 'description': description, 
            'created_at': datetime.datetime.utcnow()
        })
        return True, None
    except Exception as e: return False, str(e)

def revoke_api_key_db(client_id):
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    client['api_gateway_db']['api_keys'].delete_one({'client_id': client_id})
    return True, None

# --- Rate Limiter & Auth ---
def get_client_id():
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        client, _ = get_db_connection()
        if client:
            key_doc = client['api_gateway_db']['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc: return key_doc['client_id']
    return get_remote_address()

limiter = Limiter(key_func=get_client_id, app=app, default_limits=["2000 per day", "500 per hour"], storage_uri="memory://")

def require_api_key(f):
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS': return jsonify({'status': 'ok'}), 200
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Auth required"}), 401
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
    <title>API Gateway V2</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #121212; color: #e0e0e0; }
        .card { background-color: #1e1e1e; border: 1px solid #333; margin-bottom: 20px; }
        .sidebar { min-height: 100vh; background-color: #191919; border-right: 1px solid #333; }
        .nav-link { color: #aaa; }
        .nav-link:hover, .nav-link.active { color: #fff; background-color: #333; border-radius: 5px; }
        .status-dot { height: 12px; width: 12px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .dot-green { background-color: #28a745; box-shadow: 0 0 5px #28a745; }
        .dot-red { background-color: #dc3545; box-shadow: 0 0 5px #dc3545; }
        .log-timestamp { font-family: monospace; color: #88c0d0; }
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
                <div class="mt-auto pt-4 border-top border-secondary small text-muted">
                    Versie 2.2 (Full Stats)
                </div>
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
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // Tijdzone conversie script
        document.addEventListener("DOMContentLoaded", function() {
            document.querySelectorAll('.utc-timestamp').forEach(element => {
                const utcTime = element.dataset.utc;
                if (utcTime) {
                    const date = new Date(utcTime + 'Z'); 
                    if (!isNaN(date)) {
                        element.textContent = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
                    }
                }
            });
        });
    </script>
    {% if page == 'dashboard' %}
    <script>
        const chartData = JSON.parse(document.getElementById('chart-data').textContent);
        const ctx = document.getElementById('activityChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: 'Requests',
                    data: chartData.counts,
                    backgroundColor: 'rgba(13, 110, 253, 0.6)',
                    borderColor: '#0d6efd', borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                scales: { y: { beginAtZero: true, grid: { color: '#333' } }, x: { grid: { color: '#333' } } }
            }
        });
    </script>
    {% endif %}
</body>
</html>
"""

DASHBOARD_CONTENT = """
    <h2 class="mb-4">Systeem Overzicht</h2>
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card p-3">
                <h5 class="text-muted">Status</h5>
                <div class="d-flex align-items-center mt-2">
                    {% if db_connected %}
                        <span class="status-dot dot-green"></span> <h4 class="m-0">Online</h4>
                    {% else %}
                        <span class="status-dot dot-red"></span> <h4 class="m-0">Offline</h4>
                    {% endif %}
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3">
                <h5 class="text-muted">Requests (24u)</h5>
                <h3 class="mt-2">{{ stats_count }}</h3>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3">
                <h5 class="text-muted">Actieve Clients</h5>
                <h3 class="mt-2">{{ client_count }}</h3>
            </div>
        </div>
         <div class="col-md-3">
            <div class="card p-3 border-info">
                <h5 class="text-info">Totale Opslag</h5>
                <h3 class="mt-2">{{ total_storage }}</h3>
            </div>
        </div>
    </div>

    <div class="row">
        <div class="col-md-8">
            <div class="card p-3">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="m-0">Activiteit</h5>
                    <div class="dropdown">
                        <button class="btn btn-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
                            {{ current_range_label }}
                        </button>
                        <ul class="dropdown-menu dropdown-menu-dark">
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='6h') }}">Laatste 6 Uur</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='24h') }}">Laatste 24 Uur</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='7d') }}">Laatste Week</a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='30d') }}">Laatste Maand</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='365d') }}">Laatste Jaar</a></li>
                        </ul>
                    </div>
                </div>
                <script id="chart-data" type="application/json">{{ chart_data | tojson | safe }}</script>
                <canvas id="activityChart" height="100"></canvas>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card p-3">
                <h5 class="card-title">Top Clients (24u)</h5>
                <ul class="list-group list-group-flush mt-3">
                    {% for client in clients %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between">
                        <a href="{{ url_for('client_detail', source_app=client) }}" class="text-info text-decoration-none">{{ client }}</a>
                        <span class="badge bg-primary">Actief</span>
                    </li>
                    {% else %}
                    <li class="list-group-item bg-transparent text-muted">Geen verkeer</li>
                    {% endfor %}
                </ul>
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
            <div class="card h-100 {{ 'border-info' if ep.system else '' }}">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="m-0 font-monospace {{ 'text-info' if ep.system else 'text-white' }}">
                        /api/{{ ep.name }} 
                        {% if ep.system %}<i class="bi bi-shield-lock-fill small ms-1" title="Systeem Endpoint"></i>{% endif %}
                    </h5>
                    {% if not ep.system %}
                    <form method="POST" action="/endpoints/delete" onsubmit="return confirm('LET OP: Dit verwijdert alle data in {{ ep.name }}. Doorgaan?');">
                        <input type="hidden" name="name" value="{{ ep.name }}">
                        <button type="submit" class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button>
                    </form>
                    {% endif %}
                </div>
                <div class="card-body">
                    <p class="text-muted small">{{ ep.description }}</p>
                    <div class="row text-center mt-3">
                        <div class="col-6 border-end border-secondary">
                            <small class="text-muted">Records</small>
                            <div class="fs-5">{{ ep.stats.count }}</div>
                        </div>
                        <div class="col-6">
                            <small class="text-muted">Opslag</small>
                            <div class="fs-5 text-warning">{{ ep.stats.size }}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        {% else %}
        <div class="col-12 text-center text-muted py-5">
            <h4>Geen endpoints gevonden.</h4>
        </div>
        {% endfor %}
    </div>

    <!-- Modal -->
    <div class="modal fade" id="addEndpointModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content bg-dark text-white border-secondary">
                <div class="modal-header border-secondary">
                    <h5 class="modal-title">Endpoint Toevoegen</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <form method="POST" action="/endpoints">
                    <div class="modal-body">
                        <div class="mb-3">
                            <label class="form-label">Naam (URL pad)</label>
                            <div class="input-group">
                                <span class="input-group-text bg-secondary text-white">/api/</span>
                                <input type="text" name="name" class="form-control bg-black text-white" required pattern="[a-zA-Z0-9_]+" placeholder="products">
                            </div>
                            <div class="form-text text-muted">Gereserveerd: 'data'</div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Omschrijving</label>
                            <input type="text" name="description" class="form-control bg-black text-white">
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

CLIENT_DETAIL_CONTENT = """
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2>Client: <span class="text-info">{{ source_app }}</span></h2>
        <a href="/" class="btn btn-secondary"><i class="bi bi-arrow-left"></i> Terug</a>
    </div>
    
    <!-- Client Stats Summary -->
    <div class="row mb-4">
        <div class="col-md-6">
            <div class="card p-3">
                <h5 class="text-muted">Requests (Laatste 24u)</h5>
                <h3 class="mt-2 text-primary">{{ total_requests }}</h3>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card p-3">
                <h5 class="text-muted">Authenticatie</h5>
                <div class="mt-2">
                    {% if has_key %}
                        <span class="badge bg-success fs-5"><i class="bi bi-key-fill"></i> API Key Actief</span>
                    {% else %}
                        <span class="badge bg-danger fs-5"><i class="bi bi-exclamation-triangle-fill"></i> Geen Key</span>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>

    <div class="card p-4">
        <h5 class="card-title mb-3">Laatste 20 Logregels</h5>
        <table class="table table-dark table-striped table-hover">
            <thead>
                <tr>
                    <th>Tijd (Lokaal)</th>
                    <th>Actie</th>
                    <th>Endpoint</th>
                </tr>
            </thead>
            <tbody>
                {% for log in logs %}
                <tr>
                    <td class="utc-timestamp log-timestamp" data-utc="{{ log.timestamp }}"></td>
                    <td>{{ log.action }}</td>
                    <td><span class="badge bg-secondary">{{ log.endpoint }}</span></td>
                </tr>
                {% else %}
                <tr><td colspan="3" class="text-center text-muted">Geen logs.</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
"""

SETTINGS_CONTENT = """
    <h2>Instellingen</h2>
    <div class="row mt-4">
        <div class="col-md-6">
            <div class="card p-4">
                <h5>Nieuwe API Sleutel</h5>
                <form method="POST" action="/settings">
                    <div class="mb-3">
                        <input type="text" name="key_description" class="form-control bg-dark text-white" placeholder="Naam (bv. Webshop)" required>
                    </div>
                    <button type="submit" name="action" value="generate_key" class="btn btn-success">Genereer</button>
                </form>
                {% if new_key %}
                <div class="alert alert-success mt-3">
                    <strong>Nieuwe Key:</strong> <code class="user-select-all">{{ new_key }}</code>
                    <div class="small mt-1">Kopieer dit, het wordt niet meer getoond.</div>
                </div>
                {% endif %}
            </div>
            
            <div class="card p-4 mt-3">
                 <h5>Database Connection</h5>
                 <form method="POST" action="/settings">
                    <div class="mb-3">
                        <input type="text" name="mongo_uri" class="form-control bg-dark text-white" value="{{ current_uri }}">
                    </div>
                    <button type="submit" name="action" value="save_uri" class="btn btn-primary">Opslaan & Testen</button>
                 </form>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card p-4">
                <h5>Actieve Sleutels</h5>
                <ul class="list-group list-group-flush">
                    {% for id, data in api_keys.items() %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between">
                        <div>{{ data.description }} <small class="text-muted">({{ id }})</small></div>
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
    time_range = request.args.get('range', '6h')
    
    # Uitgebreide range map met 30d en 365d
    range_map = {
        '6h': {'delta': datetime.timedelta(hours=6), 'label': 'Laatste 6 uur', 'group': '%H:00', 'fill': 'hour'},
        '24h': {'delta': datetime.timedelta(hours=24), 'label': 'Laatste 24 uur', 'group': '%H:00', 'fill': 'hour'},
        '7d': {'delta': datetime.timedelta(days=7), 'label': 'Laatste Week', 'group': '%a %d', 'fill': 'day'},
        '30d': {'delta': datetime.timedelta(days=30), 'label': 'Laatste Maand', 'group': '%d %b', 'fill': 'day'},
        '365d': {'delta': datetime.timedelta(days=365), 'label': 'Laatste Jaar', 'group': '%b %Y', 'fill': 'month'},
    }
    
    current_range = range_map.get(time_range, range_map['6h'])
    start_time = datetime.datetime.utcnow() - current_range['delta']
    
    client, _ = get_db_connection()
    db_connected = client is not None
    stats_count = 0
    unique_clients = []
    chart_data = {"labels": [], "counts": []}
    total_size = 0

    if db_connected:
        try:
            db = client['api_gateway_db']
            yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            stats_count = db['statistics'].count_documents({'timestamp': {'$gte': yesterday}})
            unique_clients = db['statistics'].distinct('source', {'timestamp': {'$gte': yesterday}})
            
            # Totale opslag
            endpoints = get_configured_endpoints()
            for ep in endpoints:
                 try: 
                    coll_name = 'app_data' if ep['name'] == 'data' else f"data_{ep['name']}"
                    s = db.command("collstats", coll_name)
                    total_size += s.get('storageSize', 0)
                 except: pass

            # Chart Data Aggregation
            pipeline = [
                {'$match': {'timestamp': {'$gte': start_time}}},
                {'$group': {
                    '_id': {'$dateToString': {'format': current_range['group'], 'date': '$timestamp'}}, 
                    'count': {'$sum': 1},
                    'latest_time': {'$max': '$timestamp'}
                }},
                {'$sort': {'latest_time': 1}}
            ]
            agg_dict = {item['_id']: item['count'] for item in list(db['statistics'].aggregate(pipeline))}
            
            # Chart vullen (gaten opvullen met 0)
            current = start_time
            now = datetime.datetime.utcnow()
            
            if current_range['fill'] == 'hour':
                step = datetime.timedelta(hours=1)
                while current < now:
                    label = current.strftime(current_range['group'])
                    chart_data['labels'].append(label)
                    chart_data['counts'].append(agg_dict.get(label, 0))
                    current += step
            elif current_range['fill'] == 'day':
                step = datetime.timedelta(days=1)
                while current < now:
                    label = current.strftime(current_range['group'])
                    chart_data['labels'].append(label)
                    chart_data['counts'].append(agg_dict.get(label, 0))
                    current += step
            elif current_range['fill'] == 'month':
                current = datetime.datetime(current.year, current.month, 1)
                while current < now:
                    label = current.strftime(current_range['group'])
                    chart_data['labels'].append(label)
                    chart_data['counts'].append(agg_dict.get(label, 0))
                    # Maand ophogen
                    nm = current.month + 1
                    ny = current.year
                    if nm > 12:
                        nm = 1
                        ny += 1
                    current = datetime.datetime(ny, nm, 1)
                
        except Exception as e:
            print(f"Chart Error: {e}")
            pass
            
    content = render_template_string(DASHBOARD_CONTENT,
        db_connected=db_connected, stats_count=stats_count, client_count=len(unique_clients),
        clients=unique_clients, chart_data=chart_data, total_storage=format_size(total_size),
        time_range=time_range, current_range_label=current_range['label'])
    return render_template_string(BASE_LAYOUT, page='dashboard', page_content=content)

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
    for ep in endpoints:
        ep['stats'] = get_endpoint_stats(ep['name'])
    content = render_template_string(ENDPOINTS_CONTENT, endpoints=endpoints)
    return render_template_string(BASE_LAYOUT, page='endpoints', page_content=content)

@app.route('/endpoints/delete', methods=['POST'])
def delete_endpoint_route():
    name = request.form.get('name')
    if delete_endpoint(name): flash(f"Endpoint '{name}' verwijderd.", "warning")
    else: flash("Kon endpoint niet verwijderen.", "danger")
    return redirect(url_for('endpoints_page'))

@app.route('/client/<source_app>')
def client_detail(source_app):
    client, _ = get_db_connection()
    logs = []
    total_requests = 0
    has_key = False
    
    if client:
        db = client['api_gateway_db']
        # Totaal aantal requests (24u)
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        total_requests = db['statistics'].count_documents({'source': source_app, 'timestamp': {'$gte': yesterday}})
        
        # Check of client een API key heeft
        if db['api_keys'].find_one({'client_id': source_app}):
            has_key = True

        cursor = db['statistics'].find({'source': source_app}).sort('timestamp', -1).limit(20)
        for doc in cursor:
            logs.append({
                'timestamp': doc['timestamp'].isoformat(), # Raw ISO voor JS conversie
                'action': doc.get('action', '-'),
                'endpoint': doc.get('endpoint', 'general')
            })
            
    content = render_template_string(CLIENT_DETAIL_CONTENT, 
                                   source_app=source_app, 
                                   logs=logs,
                                   total_requests=total_requests,
                                   has_key=has_key)
    return render_template_string(BASE_LAYOUT, page='detail', page_content=content)

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
        elif action == 'revoke_key':
            revoke_api_key_db(request.form.get('client_id'))
        elif action == 'save_uri':
            app.config['MONGO_URI'] = request.form.get('mongo_uri')
            flash("URI opgeslagen", "info")
        return redirect(url_for('settings'))

    new_key = session.pop('new_key', None)
    content = render_template_string(SETTINGS_CONTENT, api_keys=load_api_keys(), new_key=new_key, current_uri=app.config['MONGO_URI'])
    return render_template_string(BASE_LAYOUT, page='settings', page_content=content)

@app.route('/api/health')
def health():
    client, _ = get_db_connection()
    return jsonify({"status": "running", "db": "ok" if client else "error"})

# --- DYNAMIC API ENDPOINT (General) ---
@app.route('/api/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
@require_api_key
@limiter.limit("1000 per hour")
def handle_dynamic_endpoint(endpoint_name):
    client, _ = get_db_connection()
    if not client: return jsonify({"error": "DB failure"}), 503
    db = client['api_gateway_db']
    
    if endpoint_name != 'data' and not db['endpoints'].find_one({'name': endpoint_name}):
        return jsonify({"error": f"Endpoint '{endpoint_name}' not found"}), 404

    coll_name = 'app_data' if endpoint_name == 'data' else f"data_{endpoint_name}"
    collection = db[coll_name]
    client_id = getattr(request, 'client_id', 'unknown')

    if request.method == 'POST':
        data = request.json
        if not data: return jsonify({"error": "No JSON"}), 400
        result = collection.insert_one({
            "data": data,
            "meta": {"created_at": datetime.datetime.utcnow(), "client_id": client_id}
        })
        log_statistic("post_data", client_id, endpoint_name)
        # Return ID to be used by frontend
        return jsonify({"status": "created", "id": str(result.inserted_id)}), 201

    elif request.method == 'GET':
        query = {}
        # Support basic query filtering
        for k, v in request.args.items():
            if k != '_limit': query[f"data.{k}"] = v
            
        limit = int(request.args.get('_limit', 50))
        # Fetch with _id but we'll rename it
        docs = list(collection.find(query).sort("meta.created_at", -1).limit(limit))
        
        # Transform _id to string id
        result_docs = []
        for d in docs:
            d['id'] = str(d['_id'])
            del d['_id']
            result_docs.append(d)
            
        log_statistic("read_data", client_id, endpoint_name)
        return jsonify(result_docs), 200

    elif request.method == 'DELETE':
        # Bulk delete support via query params (e.g. ?projectId=123)
        query = {}
        for k, v in request.args.items():
            query[f"data.{k}"] = v
        
        if not query:
             return jsonify({"error": "DELETE requires query parameters for safety"}), 400

        result = collection.delete_many(query)
        log_statistic("delete_bulk", client_id, endpoint_name)
        return jsonify({"status": "deleted", "count": result.deleted_count}), 200

    return jsonify({"error": "Method not allowed"}), 405

# --- SINGLE DOCUMENT OPERATIONS ---
@app.route('/api/<endpoint_name>/<doc_id>', methods=['GET', 'PUT', 'DELETE'])
@require_api_key
@limiter.limit("1000 per hour")
def handle_single_document(endpoint_name, doc_id):
    client, _ = get_db_connection()
    if not client: return jsonify({"error": "DB failure"}), 503
    db = client['api_gateway_db']

    coll_name = 'app_data' if endpoint_name == 'data' else f"data_{endpoint_name}"
    collection = db[coll_name]
    client_id = getattr(request, 'client_id', 'unknown')

    try:
        oid = ObjectId(doc_id)
    except:
        return jsonify({"error": "Invalid ID format"}), 400

    if request.method == 'GET':
        doc = collection.find_one({'_id': oid})
        if not doc: return jsonify({"error": "Not found"}), 404
        doc['id'] = str(doc['_id'])
        del doc['_id']
        log_statistic("read_one", client_id, endpoint_name)
        return jsonify(doc), 200

    elif request.method == 'PUT':
        data = request.json
        if not data: return jsonify({"error": "No JSON"}), 400
        
        # We merge updates into the 'data' field
        update_fields = {f"data.{k}": v for k, v in data.items()}
        update_fields["meta.updated_at"] = datetime.datetime.utcnow()
        
        result = collection.update_one({'_id': oid}, {'$set': update_fields})
        
        if result.matched_count == 0:
            return jsonify({"error": "Not found"}), 404
            
        # Return updated document
        updated_doc = collection.find_one({'_id': oid})
        updated_doc['id'] = str(updated_doc['_id'])
        del updated_doc['_id']
        log_statistic("update_one", client_id, endpoint_name)
        return jsonify(updated_doc), 200

    elif request.method == 'DELETE':
        result = collection.delete_one({'_id': oid})
        if result.deleted_count == 0:
            return jsonify({"error": "Not found"}), 404
        log_statistic("delete_one", client_id, endpoint_name)
        return jsonify({"status": "deleted"}), 204

    return jsonify({"error": "Method not allowed"}), 405

if __name__ == '__main__':
    get_db_connection()
    app.run(host='0.0.0.0', port=5000, debug=True)
