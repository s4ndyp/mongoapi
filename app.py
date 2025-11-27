import os
import datetime
import json
import secrets # Voor API Key authenticatie
import string # Voor random key generatie
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, abort, session
from flask_cors import CORS 
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from flask_limiter import Limiter # Voor Rate Limiting
from flask_limiter.util import get_remote_address # Nodig voor Limiter

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
MONGO_CLIENT = None

# --- Helper voor Key Generatie ---
def generate_random_key(length=20):
    """Genereert een willekeurige alfanumerieke sleutel van opgegeven lengte."""
    characters = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(characters) for _ in range(length))

# --- Helper Functies ---

def ensure_indexes(db):
    """Zorgt ervoor dat de benodigde MongoDB-indexen bestaan."""
    try:
        # 1. Index voor log historie (oorspronkelijk)
        db['app_data'].create_index([("source_app", 1), ("timestamp", -1)], background=True)
        db['statistics'].create_index([("timestamp", 1), ("source", 1)], background=True)
        
        # 2. Indexen voor API Keys
        db['api_keys'].create_index("key", unique=True, background=True)
        
        # 3. NIEUW: Index voor de actuele status (Cloud Sync)
        # Zorgt ervoor dat item_id uniek is per gebruiker (source_app)
        db['active_state'].create_index([("source_app", 1), ("item_id", 1)], unique=True, name="unique_item_per_user", background=True)
        
        print("MongoDB Indexen gecontroleerd/aangemaakt.")
    except Exception as e:
        print(f"Waarschuwing bij aanmaken indexen: {e}")

def get_db_connection(uri=None):
    """Beheert de verbinding met MongoDB."""
    global MONGO_CLIENT
    target_uri = uri if uri else app.config.get('MONGO_URI')

    if not target_uri:
        return None, "MongoDB URI is niet geconfigureerd."

    # Als er al een client is en we geen specifieke URI testen, hergebruik de connectie
    if MONGO_CLIENT is None or uri is not None:
        try:
            client = MongoClient(target_uri, serverSelectionTimeoutMS=5000)
            # Test commando
            client.admin.command('ping') 
            
            if uri is None:
                MONGO_CLIENT = client
            else: 
                # Als we alleen testen (bij settings save), return de tijdelijke client
                return client, None
            
            # Initialiseer database en indexen
            db = MONGO_CLIENT['api_gateway_db']
            ensure_indexes(db)
            return MONGO_CLIENT, None
        except Exception as e:
            return None, str(e)
            
    try:
        # Check of bestaande connectie nog leeft
        MONGO_CLIENT.admin.command('ping') 
        return MONGO_CLIENT, None
    except Exception as e:
        # Connectie verloren, reset global
        MONGO_CLIENT = None
        return None, str(e)

# --- Database Key Management ---

def load_api_keys():
    client, error = get_db_connection()
    if not client: return {}
    db = client['api_gateway_db']
    keys = {}
    try:
        for doc in db['api_keys'].find({}):
            keys[doc['client_id']] = {'key': doc['key'], 'description': doc['description']}
        return keys
    except:
        return {}

def save_new_api_key(client_id, key, description):
    client, error = get_db_connection()
    if not client: return False, "DB Error"
    try:
        client['api_gateway_db']['api_keys'].insert_one({
            'client_id': client_id,
            'key': key,
            'description': description,
            'created_at': datetime.datetime.utcnow()
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

# --- Statistieken Logger ---
def log_statistic(event_type, source="system"):
    client, _ = get_db_connection()
    if client:
        try:
            client['api_gateway_db']['statistics'].insert_one({
                "timestamp": datetime.datetime.utcnow(),
                "event": event_type,
                "source": source
            })
        except:
            pass 

# --- APP SETUP ---
app = Flask(__name__)
# Sta CORS toe voor alle domeinen, inclusief Localhost headers
CORS(app, resources={r"/api/*": {"origins": "*"}}) 

app.config['MONGO_URI'] = DEFAULT_MONGO_URI
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-voor-sessies')

# Helper om client ID te bepalen voor Rate Limiting
def get_client_id_for_limiter():
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        # Probeer key snel in DB te vinden (zou caching kunnen gebruiken voor performance)
        client, _ = get_db_connection()
        if client:
            key_doc = client['api_gateway_db']['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc:
                return key_doc['client_id']
    return get_remote_address()

# Rate Limiter instellen
limiter = Limiter(
    key_func=get_client_id_for_limiter,
    app=app,
    default_limits=["5000 per day", "500 per hour"], # Iets ruimer gezet voor sync
    storage_uri="memory://" 
)

# --- Decorator voor API Beveiliging ---
def require_api_key(f):
    def wrapper(*args, **kwargs):
        # Allow OPTIONS requests for CORS preflight without authentication
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)
            
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authenticatie vereist. Gebruik header 'Authorization: Bearer <JOUW_KEY>'"}), 401
        
        token = auth_header.split(' ')[1]
        
        client, error = get_db_connection()
        if not client:
            return jsonify({"error": "Database onbereikbaar voor verificatie"}), 503
            
        key_doc = client['api_gateway_db']['api_keys'].find_one({'key': token})
        
        if key_doc:
            # Voeg client ID toe aan request context zodat we weten WIE data stuurt
            request.client_id = key_doc['client_id']
            return f(*args, **kwargs)
        else:
            log_statistic("failed_auth_attempt", get_remote_address())
            return jsonify({"error": "Ongeldige API-sleutel"}), 401
            
    wrapper.__name__ = f.__name__ 
    return wrapper

# --- ROUTES (HTML Dashboard) ---

@app.route('/')
def dashboard():
    """Toont het dashboard met statistieken."""
    client, error = get_db_connection()
    db_status = "Online" if client else "Offline"
    error_msg = error if error else ""
    
    stats = {}
    if client:
        try:
            db = client['api_gateway_db']
            stats['total_logs'] = db['app_data'].count_documents({})
            stats['active_keys'] = db['api_keys'].count_documents({})
            # Nieuw: Tel hoeveel actieve items er in de cloud staan
            stats['synced_items'] = db['active_state'].count_documents({})
            
            # Laatste logs ophalen
            recent_logs = list(db['statistics'].find().sort("timestamp", -1).limit(10))
            for log in recent_logs:
                log['timestamp'] = log['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        except:
            recent_logs = []
            stats['total_logs'] = "Error"
    else:
        recent_logs = []

    return render_template_string(
        BASE_LAYOUT, 
        page='dashboard', 
        page_content=render_template_string(
            DASHBOARD_CONTENT, 
            db_status=db_status, 
            db_error=error_msg,
            stats=stats,
            logs=recent_logs
        )
    )

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Pagina voor configuratie en key beheer."""
    msg = None
    msg_type = "info"
    
    # Verwerk formulier acties
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_uri':
            new_uri = request.form.get('mongo_uri')
            # Test verbinding
            client, error = get_db_connection(new_uri)
            if client:
                app.config['MONGO_URI'] = new_uri
                # Reset global client om reconnection te forceren met nieuwe URI
                global MONGO_CLIENT
                MONGO_CLIENT = None 
                msg = "MongoDB URI opgeslagen en verbonden!"
                msg_type = "success"
            else:
                msg = f"Kon niet verbinden: {error}"
                msg_type = "danger"
                
        elif action == 'generate_key':
            description = request.form.get('key_description', 'Nieuwe Client')
            new_key = generate_random_key(32)
            # Maak een leesbare ID
            client_id = description.lower().replace(' ', '_') + '_' + str(secrets.randbelow(9999))
            
            success, err = save_new_api_key(client_id, new_key, description)
            if success:
                session['new_key'] = new_key
                session['new_key_desc'] = description
                msg = "Nieuwe API Key aangemaakt!"
                msg_type = "success"
            else:
                msg = f"Fout bij aanmaken key: {err}"
                msg_type = "danger"
        
        elif action == 'revoke_key':
            c_id = request.form.get('client_id')
            if revoke_api_key_db(c_id):
                msg = f"Key voor {c_id} ingetrokken."
                msg_type = "warning"

    # Data ophalen voor weergave
    api_keys = load_api_keys()
    
    # Check of er net een key is aangemaakt (eenmalig tonen)
    new_generated_key = session.pop('new_key', None)
    new_generated_desc = session.pop('new_key_desc', None)

    return render_template_string(
        BASE_LAYOUT, 
        page='settings', 
        page_content=render_template_string(
            SETTINGS_CONTENT,
            current_uri=app.config.get('MONGO_URI', ''),
            api_keys=api_keys,
            msg=msg,
            msg_type=msg_type,
            new_key=new_generated_key,
            new_key_desc=new_generated_desc
        )
    )

# --- API ENDPOINTS (GET & POST voor Cloud Sync) ---

@app.route('/api/health', methods=['GET'])
def health_check():
    client, error = get_db_connection()
    status = {
        "service": "running",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "database": "connected" if client else "disconnected"
    }
    if error:
        status["error"] = error
    return jsonify(status), 200 if client else 503

@app.route('/api/data', methods=['GET', 'POST', 'OPTIONS'])
@require_api_key
def handle_data():
    """
    Endpoint voor data synchronisatie.
    GET: Haalt actuele staat op.
    POST: Slaat updates op (logt historie EN update actuele staat).
    """
    
    # Haal Client ID op (ingesteld door de decorator)
    source_app = getattr(request, 'client_id', 'unknown_client')
    
    client, error = get_db_connection()
    if not client:
        log_statistic('db_failed_request', source_app)
        return jsonify({"error": "Database not connected", "details": error}), 503
    
    db = client['api_gateway_db']

    # --- 1. GET Request: Data Ophalen (Sync Down) ---
    if request.method == 'GET':
        try:
            # Haal alleen documenten op van DEZE specifieke API Key (source_app)
            # Dit is cruciaal voor veiligheid: Client A ziet niet Client B's data
            cursor = db['active_state'].find({'source_app': source_app})
            
            projects = []
            items = []
            
            for doc in cursor:
                # Haal het originele object uit de 'data' wrapper
                entity = doc.get('data', {})
                
                # Sorteer logica: Heeft het 'type' (task/note) of alleen 'name' (project)?
                # We baseren dit op de frontend structuur
                if 'name' in entity and 'content' not in entity:
                    projects.append(entity)
                else:
                    items.append(entity)
            
            log_statistic('sync_download', source_app)
            
            return jsonify({
                "status": "success",
                "projects": projects,
                "items": items,
                "count": len(projects) + len(items)
            }), 200
            
        except Exception as e:
            return jsonify({"error": f"Failed to fetch data: {str(e)}"}), 500

    # --- 2. POST Request: Data Opslaan (Sync Up) ---
    elif request.method == 'POST':
        try:
            payload = request.json
            if not payload:
                return jsonify({"error": "Missing JSON data"}), 400

            action = payload.get('action', 'unknown')
            item_id = payload.get('item_id')
            full_data = payload.get('full_data')
            
            # STAP A: Altijd loggen naar de historie (Audit Trail)
            # Dit bewaart elke wijziging, zelfs als je iets verwijdert
            db['app_data'].insert_one({
                'timestamp': datetime.datetime.utcnow(),
                'source_app': source_app,
                'action': action,
                'payload': payload
            })
            
            # STAP B: Update de 'Active State' (De Cloud Database)
            if item_id:
                if action.startswith('save_'):
                    # UPSERT: Update als bestaat, anders maak aan
                    # Filter op item_id EN source_app (zodat je geen items van anderen overschrijft)
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
                    # DELETE: Verwijder uit de actieve lijst
                    db['active_state'].delete_one({
                        'source_app': source_app, 
                        'item_id': item_id
                    })
            
            log_statistic('sync_upload', source_app)
            return jsonify({"status": "success", "action": action, "client": source_app}), 201

        except Exception as e:
            log_statistic('db_write_error', source_app)
            return jsonify({"error": f"Failed to process data: {str(e)}"}), 500

# --- HTML TEMPLATES (Ingebakken in bestand zoals gevraagd) ---

BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="nl" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Gateway Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .card { background-color: #1e1e1e; border: 1px solid #333; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .card-header { border-bottom: 1px solid #333; background-color: #252525; font-weight: 600; }
        .form-control, .form-select { background-color: #2c2c2c; border: 1px solid #444; color: #fff; }
        .form-control:focus { background-color: #333; color: #fff; border-color: #0d6efd; }
        .sidebar { min-height: 100vh; background-color: #191919; border-right: 1px solid #333; }
        .nav-link { color: #aaa; margin-bottom: 5px; border-radius: 5px; }
        .nav-link:hover { background-color: #2a2a2a; color: #fff; }
        .nav-link.active { background-color: #0d6efd; color: #fff; }
        .nav-link i { margin-right: 10px; }
        .status-dot { height: 10px; width: 10px; background-color: #bbb; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .status-online { background-color: #198754; }
        .status-offline { background-color: #dc3545; }
        pre { background: #111; padding: 10px; border-radius: 5px; border: 1px solid #333; color: #00ff9d; }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            <!-- Sidebar -->
            <nav class="col-md-3 col-lg-2 d-md-block sidebar collapse p-3">
                <a href="/" class="d-flex align-items-center mb-3 mb-md-0 me-md-auto text-white text-decoration-none">
                    <i class="bi bi-hdd-network fs-4 me-2"></i>
                    <span class="fs-4">Gateway</span>
                </a>
                <hr>
                <ul class="nav flex-column">
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if page=='dashboard' else '' }}" href="/">
                            <i class="bi bi-speedometer2"></i> Dashboard
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if page=='settings' else '' }}" href="/settings">
                            <i class="bi bi-gear"></i> Instellingen
                        </a>
                    </li>
                </ul>
                <hr>
                <div class="dropdown">
                    <a href="#" class="d-flex align-items-center text-white text-decoration-none dropdown-toggle" id="dropdownUser1" data-bs-toggle="dropdown" aria-expanded="false">
                        <i class="bi bi-person-circle me-2"></i>
                        <strong>Admin</strong>
                    </a>
                </div>
            </nav>

            <!-- Main Content -->
            <main class="col-md-9 ms-sm-auto col-lg-10 px-md-4 py-4">
                {{ page_content | safe }}
            </main>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

DASHBOARD_CONTENT = """
<div class="d-flex justify-content-between flex-wrap flex-md-nowrap align-items-center pb-2 mb-3 border-bottom border-secondary">
    <h1 class="h2">Dashboard</h1>
    <div class="btn-toolbar mb-2 mb-md-0">
        <span class="badge bg-dark border border-secondary p-2 d-flex align-items-center">
            <span class="status-dot {{ 'status-online' if db_status=='Online' else 'status-offline' }}"></span>
            MongoDB: {{ db_status }}
        </span>
    </div>
</div>

{% if db_error %}
<div class="alert alert-danger" role="alert">
    <i class="bi bi-exclamation-triangle-fill me-2"></i> <strong>Database Fout:</strong> {{ db_error }}
</div>
{% endif %}

<div class="row">
    <div class="col-md-4">
        <div class="card text-white">
            <div class="card-body">
                <h5 class="card-title text-muted">Totaal Logs</h5>
                <h2 class="card-text">{{ stats.total_logs }}</h2>
                <small class="text-secondary"><i class="bi bi-archive"></i> Opgeslagen events</small>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card text-white">
            <div class="card-body">
                <h5 class="card-title text-muted">Cloud Items</h5>
                <h2 class="card-text text-info">{{ stats.synced_items }}</h2>
                <small class="text-secondary"><i class="bi bi-cloud-check"></i> Actieve taken/projecten</small>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card text-white">
            <div class="card-body">
                <h5 class="card-title text-muted">Actieve Clients</h5>
                <h2 class="card-text text-success">{{ stats.active_keys }}</h2>
                <small class="text-secondary"><i class="bi bi-key"></i> Uitgegeven API Keys</small>
            </div>
        </div>
    </div>
</div>

<h3 class="mt-4 mb-3">Recente Activiteit</h3>
<div class="table-responsive card p-0">
    <table class="table table-dark table-hover mb-0">
        <thead>
            <tr>
                <th>Tijdstip</th>
                <th>Event</th>
                <th>Bron (Client ID)</th>
            </tr>
        </thead>
        <tbody>
            {% for log in logs %}
            <tr>
                <td>{{ log.timestamp }}</td>
                <td>{{ log.event }}</td>
                <td><span class="badge bg-secondary">{{ log.source }}</span></td>
            </tr>
            {% else %}
            <tr><td colspan="3" class="text-center text-muted py-3">Geen recente logs gevonden.</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

SETTINGS_CONTENT = """
<div class="d-flex justify-content-between flex-wrap flex-md-nowrap align-items-center pb-2 mb-3 border-bottom border-secondary">
    <h1 class="h2">Instellingen</h1>
</div>

{% if msg %}
<div class="alert alert-{{ msg_type }} alert-dismissible fade show" role="alert">
    {{ msg }}
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
</div>
{% endif %}

<div class="row">
    <!-- Database Config -->
    <div class="col-md-6">
        <div class="card h-100">
            <div class="card-header"><i class="bi bi-database me-2"></i> Database Configuratie</div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label text-muted">MongoDB URI</label>
                        <input type="text" name="mongo_uri" class="form-control font-monospace" value="{{ current_uri }}" placeholder="mongodb://...">
                        <div class="form-text text-secondary">Verbindingsstring naar uw MongoDB instantie.</div>
                    </div>
                    <button type="submit" name="action" value="save_uri" class="btn btn-primary">
                        <i class="bi bi-save me-1"></i> Opslaan & Verbinden
                    </button>
                </form>
            </div>
        </div>
    </div>

    <!-- API Key Manager -->
    <div class="col-md-6">
        <div class="card h-100">
            <div class="card-header"><i class="bi bi-key me-2"></i> API Access Management</div>
            <div class="card-body">
                <form method="POST" class="mb-4 border-bottom border-secondary pb-4">
                    <label class="form-label text-muted">Nieuwe Sleutel Genereren</label>
                    <div class="input-group">
                        <input type="text" name="key_description" class="form-control" placeholder="Beschrijving (bijv. iPhone App)" required>
                        <button class="btn btn-success" type="submit" name="action" value="generate_key">
                            <i class="bi bi-plus-lg"></i> Genereer
                        </button>
                    </div>
                </form>

                {% if new_key %}
                <div class="alert alert-success">
                    <h5 class="alert-heading"><i class="bi bi-check-circle"></i> Sleutel Aangemaakt!</h5>
                    <p>Kopieer deze sleutel <strong>nu</strong>. Hij wordt hierna niet meer volledig getoond.</p>
                    <hr>
                    <div class="input-group mb-2">
                        <span class="input-group-text bg-success text-white border-0">Beschrijving</span>
                        <input type="text" class="form-control bg-dark text-light" value="{{ new_key_desc }}" readonly>
                    </div>
                    <div class="input-group">
                        <span class="input-group-text bg-warning text-dark border-0">API KEY</span>
                        <input type="text" class="form-control font-monospace bg-dark text-warning fw-bold" value="{{ new_key }}" readonly onclick="this.select()">
                    </div>
                </div>
                {% endif %}

                <h6 class="text-muted mb-3">Actieve Sleutels</h6>
                <div class="list-group list-group-flush">
                    {% for client_id, data in api_keys.items() %}
                    <div class="list-group-item bg-transparent text-light d-flex justify-content-between align-items-center px-0">
                        <div>
                            <div class="fw-bold">{{ data.description }}</div>
                            <small class="text-secondary font-monospace">{{ client_id }}</small>
                        </div>
                        <form method="POST" onsubmit="return confirm('Weet u zeker dat u toegang voor {{ data.description }} wilt intrekken?');">
                            <input type="hidden" name="client_id" value="{{ client_id }}">
                            <button type="submit" name="action" value="revoke_key" class="btn btn-sm btn-outline-danger">
                                <i class="bi bi-trash"></i> Revoke
                            </button>
                        </form>
                    </div>
                    {% else %}
                    <div class="text-center text-muted py-2">Geen actieve sleutels.</div>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>
</div>
"""

if __name__ == '__main__':
    # Initialiseer de database verbinding bij opstarten
    get_db_connection()
    # Start de Flask ontwikkelserver
    app.run(host='0.0.0.0', port=5000, debug=True)
