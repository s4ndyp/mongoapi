import os
import datetime
import json
import secrets
import string
import re
from functools import wraps
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, session
from flask_cors import CORS 
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, OperationFailure
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from bson import ObjectId

# IMPORTS voor JWT en hashing
import jwt 
from bcrypt import hashpw, gensalt, checkpw

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
MONGO_CLIENT = None
app = Flask(__name__)
CORS(app) 
app.config['MONGO_URI'] = DEFAULT_MONGO_URI 
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-this')

# CONFIGURATIE VOOR JWT
app.config['JWT_SECRET'] = os.environ.get('JWT_SECRET', secrets.token_urlsafe(32))
app.config['JWT_EXPIRY_MINUTES'] = 60 * 24 # Standaard fallback (24 uur)

# --- Helper: Wachtwoord Hashing ---
def hash_password(password):
    """Gebruik bcrypt voor veilige wachtwoord hashing."""
    return hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

def check_password(password, hashed):
    """Controleer het wachtwoord tegen de hash."""
    return checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# --- Helper: JWT Functies ---
def encode_auth_token(user_id, expiry_minutes=None):
    """Genereert het Auth Token. Accepteert optionele specifieke expiry tijd."""
    try:
        # Gebruik meegegeven tijd of de global default
        minutes = expiry_minutes if expiry_minutes is not None else app.config['JWT_EXPIRY_MINUTES']
        
        payload = {
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes),
            'iat': datetime.datetime.utcnow(),
            'sub': str(user_id) # Subject is de gebruikers ID
        }
        return jwt.encode(payload, app.config.get('JWT_SECRET'), algorithm='HS256')
    except Exception as e:
        print(f"JWT Encoding Error: {e}")
        return None

def decode_auth_token(auth_token):
    """Decodeert het Auth Token - retourneert user_id of error string."""
    try:
        payload = jwt.decode(auth_token, app.config.get('JWT_SECRET'), algorithms=['HS256'])
        # Retourneert tuple (True, user_id) bij succes
        return (True, payload['sub'])
    except jwt.ExpiredSignatureError:
        return (False, 'Token is verlopen.')
    except jwt.InvalidTokenError:
        return (False, 'Ongeldig token.')

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
        
        # Index voor dynamische endpoints configuratie
        db['endpoints'].create_index("name", unique=True, background=True)
        
        # Index voor gebruikers (voor JWT login)
        db['users'].create_index("username", unique=True, background=True)
        
        # Indexen voor snellere project en type queries op de data
        db['data_items'].create_index([("projectId", 1), ("type", 1)], background=True)
        db['data_projects'].create_index([("name", 1)], background=True)
        
        # NIEUW: Index op meta.client_id voor snelle filtering per gebruiker
        db['data_items'].create_index("meta.client_id", background=True)
        db['data_projects'].create_index("meta.client_id", background=True)
        
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
    
    # Voeg de nieuwe Taskey endpoints toe die nu in de client worden gebruikt
    endpoints.append({
        'name': 'items',
        'description': 'Taskey Items (Taken en Notities)',
        'system': True,
        'created_at': datetime.datetime.min
    })
    endpoints.append({
        'name': 'projects',
        'description': 'Taskey Projecten',
        'system': True,
        'created_at': datetime.datetime.min
    })


    if client:
        # 2. Voeg dynamische endpoints uit DB toe
        try:
            db_endpoints = list(client['api_gateway_db']['endpoints'].find({}, {'_id': 0}).sort('name', 1))
            for ep in db_endpoints:
                if ep.get('name') not in ['data', 'items', 'projects']: # Filter de nieuwe en oude vaste endpoints
                    ep['system'] = False
                    endpoints.append(ep)
        except Exception as e:
            print(f"Fout bij ophalen endpoints: {e}")
            
    return endpoints

def get_db_collection_name(endpoint_name):
    """Bepaalt de collectienaam op basis van het endpoint."""
    if endpoint_name == 'data':
        return 'app_data'
    elif endpoint_name == 'items':
        return 'data_items'
    elif endpoint_name == 'projects':
        return 'data_projects'
    else:
        return f"data_{endpoint_name}"

def get_endpoint_stats(endpoint_name):
    client, _ = get_db_connection()
    if not client: return {'count': 0, 'size': '0 KB'}
    coll_name = get_db_collection_name(endpoint_name)
    try:
        stats = client['api_gateway_db'].command("collstats", coll_name)
        return {'count': stats.get('count', 0), 'size': format_size(stats.get('storageSize', 0))}
    except:
        return {'count': 0, 'size': '0 KB'}

def create_endpoint(name, description):
    if not re.match("^[a-zA-Z0-9_]+$", name):
        return False, "Naam mag alleen letters, cijfers en underscores bevatten."
    if name in ['data', 'items', 'projects']:
        return False, f"De naam '{name}' is gereserveerd voor het systeem."
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    try:
        client['api_gateway_db']['endpoints'].insert_one({
            'name': name, 'description': description, 'created_at': datetime.datetime.utcnow()
        })
        client['api_gateway_db'].create_collection(get_db_collection_name(name))
        return True, None
    except Exception as e: return False, str(e)

def delete_endpoint(name):
    if name in ['data', 'items', 'projects']: return False
    client, _ = get_db_connection()
    if not client: return False
    try:
        client['api_gateway_db']['endpoints'].delete_one({'name': name})
        client['api_gateway_db'][get_db_collection_name(name)].drop()
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

# --- USER MANAGEMENT FUNCTIES ---
def load_all_users():
    client, _ = get_db_connection()
    if not client: return []
    try:
        # Haal gebruikers op, zonder password_hash
        users = list(client['api_gateway_db']['users'].find({}, {'username': 1, 'created_at': 1, 'token_validity_minutes': 1}))
        return [{'username': u['username'], 'created_at': u['created_at'], 'validity': u.get('token_validity_minutes', 1440)} for u in users]
    except Exception as e:
        print(f"Error loading users: {e}")
        return []

def delete_user_db(username):
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    try:
        client['api_gateway_db']['users'].delete_one({'username': username})
        return True, None
    except Exception as e:
        return False, str(e)

# --- AUTHENTICATIE ROUTE (JWT Login) ---
@app.route('/api/auth/login', methods=['POST'])
def login_api():
    client, _ = get_db_connection()
    if not client: return jsonify({"error": "DB failure"}), 503
    
    data = request.json
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Ongeldige input: gebruikersnaam en wachtwoord vereist."}), 400
        
    username = data['username']
    password = data['password']
    
    db = client['api_gateway_db']
    user = db['users'].find_one({'username': username})
    
    if user and check_password(password, user['password_hash']):
        # Succesvol ingelogd, genereer JWT
        user_expiry = user.get('token_validity_minutes', app.config['JWT_EXPIRY_MINUTES'])
        
        token = encode_auth_token(user['_id'], user_expiry)
        
        log_statistic("login_success", username, "auth")
        return jsonify({
            "status": "success", 
            "token": token,
            "expires_in_minutes": user_expiry
        }), 200
    else:
        log_statistic("login_failed", username, "auth")
        return jsonify({"error": "Ongeldige gebruikersnaam of wachtwoord."}), 401
        
# --- Rate Limiter & Auth ---
def get_client_id():
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        client, _ = get_db_connection()
        if client:
            # 1. Probeer JWT te decoderen
            success, user_id_or_error = decode_auth_token(token)
            if success:
                # JWT is geldig. Gebruik de gebruikersnaam als client ID voor rate limiting.
                db = client['api_gateway_db']
                user = db['users'].find_one({'_id': ObjectId(user_id_or_error)}, {'username': 1})
                return user['username'] if user else f"user_{user_id_or_error}"
                
            # 2. Fallback naar API Key check (bestaande clients/dashboard)
            key_doc = client['api_gateway_db']['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc: return key_doc['client_id']
            
    return get_remote_address()

limiter = Limiter(key_func=get_client_id, app=app, default_limits=["2000 per day", "500 per hour"], storage_uri="memory://")

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS': return jsonify({'status': 'ok'}), 200
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authenticatie vereist (Bearer Token)"}), 401
            
        token = auth_header.split(' ')[1]
        client, _ = get_db_connection()
        
        # 1. Probeer JWT te decoderen
        success, user_id_or_error = decode_auth_token(token)
        
        if success:
            # JWT is geldig. Ga door met de gebruiker.
            db = client['api_gateway_db']
            try:
                # Zoek de gebruikersnaam op basis van de ID in de token
                user = db['users'].find_one({'_id': ObjectId(user_id_or_error)}, {'username': 1})
                client_id = user['username'] if user else f"user_{user_id_or_error}"
                request.client_id = client_id
                return f(*args, **kwargs)
            except Exception as e:
                # Mocht de ObjectId uit de token ongeldig zijn of de gebruiker niet bestaan
                return jsonify({"error": f"Ongeldige JWT Sub (Gebruiker niet gevonden). Detail: {e}"}), 401
        
        # 2. Als JWT faalt (user_id_or_error is een error string), probeer Legacy API Key
        jwt_error_detail = user_id_or_error # Dit is de foutmelding (bv. 'Token is verlopen.')
        client_id = None
        if client:
            db = client['api_gateway_db']
            key_doc = db['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc: client_id = key_doc['client_id']
            
        if client_id:
            # API Key is geldig
            request.client_id = client_id
            return f(*args, **kwargs)
        else:
            # Zowel JWT als API Key faalt
            return jsonify({"error": f"Ongeldige Auth Token/Key. Detail: {jwt_error_detail}"}), 401
        
    return wrapper

# --- NIEUWE DECORATOR VOOR DASHBOARD AUTHENTICATIE ---
def require_dashboard_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Controleer of de gebruikersnaam in de sessie staat
        if 'username' not in session:
            flash("Log eerst in om het dashboard te bekijken.", "warning")
            return redirect(url_for('dashboard_login'))
        return f(*args, **kwargs)
    return decorated_function
# ---------------------------------------------------

# --- HTML TEMPLATES (ongewijzigd) ---

LOGIN_CONTENT = """
    <div class="row justify-content-center pt-5">
        <div class="col-md-6 col-lg-4">
            <div class="card p-4 shadow-lg">
                <h3 class="card-title text-center mb-4 text-white"><i class="bi bi-lock-fill"></i> Dashboard Login</h3>
                {% with messages = get_flashed_messages(with_categories=true) %}
                  {% if messages %}
                    {% for category, message in messages %}
                      <div class="alert alert-{{ category }}">{{ message | safe }}</div>
                    {% endfor %}
                  {% endif %}
                {% endwith %}
                <form method="POST" action="{{ url_for('dashboard_login') }}">
                    <div class="mb-3">
                        <label for="username" class="form-label text-muted">Gebruikersnaam</label>
                        <input type="text" name="username" id="username" class="form-control bg-dark text-white" required autofocus>
                    </div>
                    <div class="mb-4">
                        <label for="password" class="form-label text-muted">Wachtwoord</label>
                        <input type="password" name="password" id="password" class="form-control bg-dark text-white" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">Log In</button>
                </form>
            </div>
        </div>
    </div>
"""

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
        .fixed-top { position: fixed; top: 0; }
        /* FIX VOOR LANGE JWT IN FLASH MESSAGE */
        .jwt-input-fix {
             width: 100%;
             word-wrap: break-word; /* Kan helpen in sommige browsers */
             min-width: 0; /* Belangrijk voor flex containers */
             height: auto; /* Zodat het invoerveld kan groeien */
        }
        /* Zorg dat de login pagina het hele scherm vult */
        {% if page == 'login' %}
        .container-fluid { height: 100vh; display: flex; align-items: center; justify-content: center; }
        {% endif %}
    </style>
</head>
<body>
    <!-- Notificatie/Toast element voor kopieren -->
    <div id="dashboard-notification" class="alert alert-success d-none fixed-top mt-3 mx-auto shadow-lg" 
        style="width: 300px; z-index: 1050; text-align: center;"></div>

    <div class="container-fluid">
        <div class="row w-100">
            {% if page != 'login' %}
            <nav class="col-md-3 col-lg-2 d-md-block sidebar collapse p-3">
                <h4 class="mb-4 text-white"><i class="bi bi-hdd-network"></i> Gateway</h4>
                <ul class="nav flex-column">
                    <li class="nav-item"><a class="nav-link {{ 'active' if page == 'dashboard' else '' }}" href="/"><i class="bi bi-speedometer2"></i> Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link {{ 'active' if page == 'endpoints' else '' }}" href="/endpoints"><i class="bi bi-diagram-3"></i> Endpoints</a></li>
                    <li class="nav-item"><a class="nav-link {{ 'active' if page == 'settings' else '' }}" href="/settings"><i class="bi bi-gear"></i> Instellingen</a></li>
                </ul>
                <div class="mt-auto pt-4 border-top border-secondary small text-muted">
                    Ingelogd als: <strong class="text-white">{{ session.get('username', 'Gast') }}</strong>
                    <div class="mt-2">
                        <a href="{{ url_for('dashboard_logout') }}" class="btn btn-sm btn-outline-danger w-100"><i class="bi bi-box-arrow-right"></i> Uitloggen</a>
                    </div>
                    <div class="mt-4">Versie 2.2 (Full Stats)</div>
                </div>
            </nav>
            {% endif %}
            
            <main class="{{ 'col-12' if page == 'login' else 'col-md-9 ms-sm-auto col-lg-10' }} px-md-4 py-4">
                {% if page != 'login' %}
                {% with messages = get_flashed_messages(with_categories=true) %}
                  {% if messages %}
                    {% for category, message in messages %}
                      <div class="alert alert-{{ category }} alert-dismissible fade show">{{ message | safe }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
                    {% endfor %}
                  {% endif %}
                {% endwith %}
                {% endif %}
                {{ page_content | safe }}
            </main>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // Functie voor notificaties
        function showNotification(message, type = 'success') {
            const notif = document.getElementById('dashboard-notification');
            // Zorg ervoor dat het element bestaat
            if (!notif) return;

            notif.className = `alert alert-${type} fixed-top mt-3 mx-auto shadow-lg`;
            notif.style.display = 'block';
            notif.innerHTML = message;
            setTimeout(() => {
                notif.style.display = 'none';
            }, 3000);
        }

        // Functie voor kopiëren naar klembord
        function copyKey(elementId) {
            const inputElement = document.getElementById(elementId);
            if (!inputElement) return;
            
            // Selecteer de tekst
            inputElement.select();
            inputElement.setSelectionRange(0, 99999); 
            
            // Kopieer de tekst via de fallback methode
            try {
                const successful = document.execCommand('copy');
                if (successful) {
                    showNotification('Token gekopieerd!', 'success'); // Aangepast naar Token
                } else {
                    showNotification('Kopiëren mislukt. Probeer handmatig te selecteren.', 'danger');
                }
            } catch (err) {
                 showNotification('Kopiëren mislukt wegens fout.', 'danger');
            }
        }
        
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
            
            // JWT Flash Message Kopieer Listener
            const jwtCopyButton = document.getElementById('jwt-copy-button');
            if (jwtCopyButton) {
                jwtCopyButton.addEventListener('click', () => {
                    copyKey('jwt-token-input');
                });
            }
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
                            <div class="form-text text-muted">Gereserveerd: 'data', 'items', 'projects'</div>
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
                    {% if is_user %}
                        <span class="badge bg-primary fs-5"><i class="bi bi-person-fill"></i> Logged in User (JWT)</span>
                    {% elif has_key %}
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
                <h5>Nieuwe Gebruiker Aanmaken</h5>
                <form method="POST" action="/settings">
                    <div class="mb-3">
                        <label class="form-label text-muted">Naam</label>
                        <input type="text" name="username" class="form-control bg-dark text-white" placeholder="Gebruikersnaam" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-muted">Wachtwoord</label>
                        <input type="password" name="password" class="form-control bg-dark text-white" placeholder="Wachtwoord" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-muted">Token Geldigheid</label>
                        <select name="token_validity_minutes" class="form-select bg-dark text-white">
                            <option value="1440" selected>24 uur</option>
                            <option value="10080">7 dagen</option>
                            <option value="44640">31 dagen</option>
                            <option value="525600">365 dagen</option>
                        </select>
                        <div class="form-text text-muted small">Dit geldt voor het eerste token én toekomstige logins.</div>
                    </div>
                    <button type="submit" name="action" value="create_user" class="btn btn-success">Gebruiker Toevoegen</button>
                </form>
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
            <div class="card p-4 mb-3">
                <h5>Actieve Gebruikers (JWT)</h5>
                <ul class="list-group list-group-flush">
                    {% for user in active_users %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between">
                        <div>
                            {{ user.username }} 
                            <small class="text-muted d-block" style="font-size: 0.8em">
                                Sinds: <span class="utc-timestamp" data-utc="{{ user.created_at.isoformat() }}"></span><br>
                                Token duur: {{ (user.validity / 60) | int }} uur
                            </small>
                        </div>
                        <form method="POST" action="/settings" onsubmit="return confirm('Gebruiker \'{{ user.username }}\' verwijderen? Dit verbreekt alle actieve JWTs van deze gebruiker!');">
                            <input type="hidden" name="action" value="delete_user">
                            <input type="hidden" name="username" value="{{ user.username }}">
                            <button class="btn btn-sm btn-danger ms-2">X</button>
                        </form>
                    </li>
                    {% else %}
                    <li class="list-group-item bg-transparent text-muted">Geen gebruikers gevonden.</li>
                    {% endfor %}
                </ul>
            </div>
            <div class="card p-4">
                <h5>Actieve API Sleutels (Legacy)</h5>
                <ul class="list-group list-group-flush">
                    {% for id, data in api_keys.items() %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between align-items-start">
                        <div class="me-3 flex-grow-1">
                            <div>{{ data.description }} <small class="text-muted">({{ id }})</small></div>
                            <div class="input-group input-group-sm mt-1">
                                <input type="text" class="form-control bg-dark text-warning small font-monospace" readonly 
                                    value="{{ data.key }}" id="key-{{ id }}">
                                <button type="button" class="btn btn-outline-info" 
                                        onclick="copyKey('key-{{ id }}')" title="Kopieer Key">
                                    <i class="bi bi-clipboard"></i>
                                </button>
                            </div>
                        </div>
                        <form method="POST" action="/settings" onsubmit="return confirm('Intrekken?');">
                            <input type="hidden" name="action" value="revoke_key">
                            <input type="hidden" name="client_id" value="{{ id }}">
                            <button class="btn btn-sm btn-danger ms-2" title="Trek in">X</button>
                        </form>
                    </li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>
"""

# --- DASHBOARD LOGIC (Web Interface Routes) ---

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per 60 second", key_func=get_remote_address, error_message="Te veel mislukte loginpogingen. Probeer het over 60 seconden opnieuw.") # NIEUW: Rate Limiting
def dashboard_login():
    if 'username' in session:
        return redirect(url_for('dashboard')) # Al ingelogd

    if request.method == 'POST':
        client, _ = get_db_connection()
        if not client: 
            flash("DB fout: Kan geen verbinding maken.", "danger")
            return redirect(url_for('dashboard_login'))
        
        username = request.form.get('username')
        password = request.form.get('password')
        
        db = client['api_gateway_db']
        user = db['users'].find_one({'username': username})
        
        if user and check_password(password, user['password_hash']):
            session['username'] = username
            flash(f"Succesvol ingelogd als {username}.", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Ongeldige gebruikersnaam of wachtwoord.", "danger")
            # Belangrijk: De limiter telt hier automatisch een mislukte POST-poging.
            return redirect(url_for('dashboard_login'))

    content = render_template_string(LOGIN_CONTENT)
    # Gebruik een kale layout zonder navigatiebalk voor de loginpagina
    return render_template_string(BASE_LAYOUT, page='login', page_content=content)

@app.errorhandler(429)
def ratelimit_handler(e):
    """
    Handler voor Rate Limit Exceeded (HTTP 429).
    Dit vangt de foutmelding van de Flask-Limiter op en zet deze om naar een
    gebruikersvriendelijke flash-message op de loginpagina.
    """
    # De foutmelding is al in de limiter gedefinieerd: "Te veel mislukte loginpogingen..."
    flash(str(e.description), "danger")
    return redirect(url_for('dashboard_login'))

@app.route('/logout')
def dashboard_logout():
    session.pop('username', None)
    flash("Je bent uitgelogd.", "info")
    return redirect(url_for('dashboard_login'))

@app.route('/')
@require_dashboard_auth # Nieuwe beveiliging
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
                    coll_name = get_db_collection_name(ep['name'])
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
@require_dashboard_auth # Nieuwe beveiliging
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
@require_dashboard_auth # Nieuwe beveiliging
def delete_endpoint_route():
    name = request.form.get('name')
    if delete_endpoint(name): flash(f"Endpoint '{name}' verwijderd.", "warning")
    else: flash("Kon endpoint niet verwijderen.", "danger")
    return redirect(url_for('endpoints_page'))

@app.route('/client/<source_app>')
@require_dashboard_auth # Nieuwe beveiliging
def client_detail(source_app):
    client, _ = get_db_connection()
    logs = []
    total_requests = 0
    has_key = False
    is_user = False
    
    if client:
        db = client['api_gateway_db']
        # Totaal aantal requests (24u)
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        total_requests = db['statistics'].count_documents({'source': source_app, 'timestamp': {'$gte': yesterday}})
        
        # Check of client een API key heeft
        if db['api_keys'].find_one({'client_id': source_app}):
            has_key = True

        # Check of client een geregistreerde gebruiker is
        if db['users'].find_one({'username': source_app}):
            is_user = True

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
                                   has_key=has_key,
                                   is_user=is_user)
    return render_template_string(BASE_LAYOUT, page='detail', page_content=content)

@app.route('/settings', methods=['GET', 'POST'])
@require_dashboard_auth # Nieuwe beveiliging
def settings():
    client, _ = get_db_connection()
    db = client['api_gateway_db'] if client else None
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        # NIEUWE LOGICA VOOR GEBRUIKERSBEHEER
        if action == 'create_user':
            username = request.form.get('username')
            password = request.form.get('password')
            # Lees de gekozen geldigheidsduur (default 24 uur / 1440 min)
            token_validity = int(request.form.get('token_validity_minutes', 1440))
            
            if db is None:
                flash("Fout: Geen DB verbinding.", "danger")
            elif not username or not password:
                flash("Fout: Gebruikersnaam en wachtwoord zijn verplicht.", "danger")
            else:
                try:
                    # 1. Gebruiker aanmaken met token voorkeur
                    result = db['users'].insert_one({
                        'username': username,
                        'password_hash': hash_password(password),
                        'created_at': datetime.datetime.utcnow(),
                        'role': 'admin',
                        'token_validity_minutes': token_validity # Opslaan van voorkeur
                    })
                    
                    # 2. JWT genereren voor de nieuwe gebruiker met specifieke expiry
                    new_user_id = result.inserted_id
                    new_token = encode_auth_token(new_user_id, token_validity)
                    
                    # Bereken dagen voor nette weergave in bericht
                    days = token_validity // 1440
                    time_msg = f"{days} dagen" if days >= 1 else "24 uur"

                    # 3. HTML fragment genereren om de token te tonen en te kopiëren
                    token_html = f"""
                    <p class="mb-2">Gebruiker **{username}** succesvol aangemaakt. Hier is het nieuwe JWT:</p>
                    <div class="d-flex align-items-center">
                        <input type="text" class="form-control bg-dark text-warning small font-monospace jwt-input-fix" readonly 
                            value="{new_token}" id="jwt-token-input">
                        <button type="button" class="btn btn-warning ms-2 flex-shrink-0" id="jwt-copy-button" title="Kopieer JWT">
                            <i class="bi bi-clipboard"></i> Kopieer Token
                        </button>
                    </div>
                    <p class="mt-2 small text-muted">Dit token is <b>{time_msg}</b> geldig.</p>
                    """
                    
                    flash(token_html, "success")
                
                except OperationFailure as e:
                    if "E11000 duplicate key" in str(e):
                        flash(f"Fout: Gebruikersnaam '{username}' bestaat al.", "danger")
                    else:
                         flash(f"Fout bij aanmaken gebruiker: {e}", "danger")
                except Exception as e:
                    flash(f"Onverwachte fout: {e}", "danger")

        elif action == 'delete_user':
            username = request.form.get('username')
            success, err = delete_user_db(username)
            if success: flash(f"Gebruiker '{username}' verwijderd. Actieve JWT's zijn ongeldig geworden.", "warning")
            else: flash(f"Fout: {err}", "danger")

        # BESTAANDE LOGICA VOOR LEGACY EN DB SETTINGS
        elif action == 'revoke_key':
            revoke_api_key_db(request.form.get('client_id'))
        elif action == 'save_uri':
            app.config['MONGO_URI'] = request.form.get('mongo_uri')
            flash("URI opgeslagen", "info")
            
        return redirect(url_for('settings'))

    api_keys = load_api_keys()
    active_users = load_all_users() # Lijst met actieve users

    content = render_template_string(SETTINGS_CONTENT, 
                                     api_keys=api_keys, 
                                     active_users=active_users,
                                     current_uri=app.config['MONGO_URI'])
    return render_template_string(BASE_LAYOUT, page='settings', page_content=content)

@app.route('/api/health')
def health():
    client, _ = get_db_connection()
    return jsonify({"status": "running", "db": "ok" if client else "error"})

# --- DYNAMIC API ENDPOINT (General) ---
@app.route('/api/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
@require_auth
@limiter.limit("1000 per hour")
def handle_dynamic_endpoint(endpoint_name):
    client, _ = get_db_connection()
    if not client: return jsonify({"error": "DB failure"}), 503
    db = client['api_gateway_db']
    
    # Controleer of het een bekend endpoint is.
    if endpoint_name not in ['data', 'items', 'projects'] and not db['endpoints'].find_one({'name': endpoint_name}):
        return jsonify({"error": f"Endpoint '{endpoint_name}' not found"}), 404

    coll_name = get_db_collection_name(endpoint_name)
    collection = db[coll_name]
    client_id = getattr(request, 'client_id', 'unknown')

    if request.method == 'POST':
        data = request.json
        if not data: return jsonify({"error": "No JSON"}), 400
        
        # --- FIX VOOR OPSLAAN VAN CLIENT DATA ---
        
        # Voeg meta-informatie toe
        data['meta'] = {"created_at": datetime.datetime.utcnow(), "client_id": client_id}
        
        try:
            result = collection.insert_one(data)
            log_statistic("post_data", client_id, endpoint_name)
            
            # Stuur het opgeslagen document terug, inclusief de nieuwe MongoDB _id
            saved_doc = collection.find_one({'_id': result.inserted_id})

            if saved_doc:
                saved_doc['id'] = str(saved_doc['_id'])
                del saved_doc['_id']
                return jsonify({"id": saved_doc['id'], "data": saved_doc}), 201
            else:
                return jsonify({"status": "created", "id": str(result.inserted_id), "data": {}}), 201

        except Exception as e:
            # Vaak een duplicate key error als de client een ID meestuurt en er een unieke index is
            print(f"MongoDB Insert Error: {e}")
            return jsonify({"error": f"Kon document niet opslaan: {e}"}), 500

    elif request.method == 'GET':
        query = {}
        # Support basic query filtering op de root velden
        for k, v in request.args.items():
            if k != '_limit': 
                # Query nu direct op root velden (bijv. 'projectId' of 'type')
                query[k] = v 
        
        # --- DATA ISOLATIE: Voeg verplicht filter toe ---
        query['meta.client_id'] = client_id
            
        limit = int(request.args.get('_limit', 50))
        
        # Fetch met _id
        docs = list(collection.find(query).sort("meta.created_at", -1).limit(limit))
        
        # Transformeer _id naar string id en stuur het volledige document terug als 'data'
        result_docs = []
        for d in docs:
            d['id'] = str(d['_id'])
            del d['_id']
            # Stuur het document terug in het client-formaat {id: 'mongo_id', data: {...document...}}
            result_docs.append({
                "id": d['id'],
                "data": d # Het volledige document
            })
            
        log_statistic("read_data", client_id, endpoint_name)
        return jsonify(result_docs), 200

    elif request.method == 'DELETE':
        # Bulk delete support via query params (e.g. ?projectId=123)
        query = {}
        for k, v in request.args.items():
            query[k] = v
        
        if not query:
             return jsonify({"error": "DELETE requires query parameters for safety"}), 400

        # --- DATA ISOLATIE: Voeg verplicht filter toe ---
        query['meta.client_id'] = client_id

        result = collection.delete_many(query)
        log_statistic("delete_bulk", client_id, endpoint_name)
        return jsonify({"status": "deleted", "count": result.deleted_count}), 200

    return jsonify({"error": "Method not allowed"}), 405

# --- SINGLE DOCUMENT OPERATIONS ---
@app.route('/api/<endpoint_name>/<doc_id>', methods=['GET', 'PUT', 'DELETE'])
@require_auth
@limiter.limit("1000 per hour")
def handle_single_document(endpoint_name, doc_id):
    client, _ = get_db_connection()
    if not client: return jsonify({"error": "DB failure"}), 503
    db = client['api_gateway_db']

    coll_name = get_db_collection_name(endpoint_name)
    collection = db[coll_name]
    client_id = getattr(request, 'client_id', 'unknown')

    try:
        oid = ObjectId(doc_id)
    except:
        return jsonify({"error": "Invalid ID format"}), 400

    if request.method == 'GET':
        doc = collection.find_one({'_id': oid})
        if not doc: return jsonify({"error": "Not found"}), 404
        
        # --- DATA ISOLATIE CHECK ---
        if doc.get('meta', {}).get('client_id') != client_id:
            # We doen alsof het niet bestaat voor beveiliging, of geven een 403 Forbidden
            return jsonify({"error": "Not found or access denied"}), 403

        doc['id'] = str(doc['_id'])
        del doc['_id']
        log_statistic("read_one", client_id, endpoint_name)
        # Formatteer voor de client: {id: 'mongo_id', data: {...document...}}
        return jsonify({"id": doc['id'], "data": doc}), 200

    elif request.method == 'PUT':
        data = request.json
        if not data: return jsonify({"error": "No JSON"}), 400
        
        # --- FIX VOOR UPDATEN VAN CLIENT DATA ---
        
        update_doc = data.copy()
        if 'id' in update_doc: del update_doc['id'] # Client stuurt dit mee
        if '_id' in update_doc: del update_doc['_id'] # Zou niet mogen, maar voor de zekerheid
        if 'meta' in update_doc: del update_doc['meta'] # Meta wordt apart gezet

        # Voeg updated_at toe aan de meta-informatie
        update_doc['meta'] = data.get('meta', {})
        update_doc['meta']['updated_at'] = datetime.datetime.utcnow()
        update_doc['meta']['client_id'] = client_id # Update of zet de client_id

        # --- DATA ISOLATIE: Update alleen als ID én ClientID matchen ---
        result = collection.update_one(
            {'_id': oid, 'meta.client_id': client_id}, 
            {'$set': update_doc}
        )
        
        if result.matched_count == 0:
            # Kan zijn dat doc niet bestaat, OF dat het van iemand anders is
            return jsonify({"error": "Not found or access denied"}), 404
            
        # Return updated document
        updated_doc = collection.find_one({'_id': oid})
        
        # Formatteer voor de client
        updated_doc['id'] = str(updated_doc['_id'])
        del updated_doc['_id']
        log_statistic("update_one", client_id, endpoint_name)
        
        return jsonify({"id": updated_doc['id'], "data": updated_doc}), 200

    elif request.method == 'DELETE':
        # --- DATA ISOLATIE: Delete alleen als ID én ClientID matchen ---
        result = collection.delete_one({'_id': oid, 'meta.client_id': client_id})
        
        if result.deleted_count == 0:
            return jsonify({"error": "Not found or access denied"}), 404
        log_statistic("delete_one", client_id, endpoint_name)
        return jsonify({"status": "deleted"}), 204

    return jsonify({"error": "Method not allowed"}), 405

if __name__ == '__main__':
    get_db_connection()
    app.run(host='0.0.0.0', port=5000, debug=True)
