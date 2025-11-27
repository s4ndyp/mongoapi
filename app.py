import os
import datetime
import json
import secrets # Voor API Key authenticatie
import string # Voor random key generatie
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, abort, session # session toegevoegd
from flask_cors import CORS 
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from flask_limiter import Limiter # Voor Rate Limiting (Feature 6)
from flask_limiter.util import get_remote_address # Nodig voor Limiter

# --- Globale Configuratie (Feature 5) ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
# Globale variabele voor de MongoClient (Connection Pooling)
MONGO_CLIENT = None


# --- Helper voor Key Generatie ---
def generate_random_key(length=20):
    """Genereert een willekeurige alfanumerieke sleutel van opgegeven lengte."""
    # Tekenset: letters, cijfers en !@#$%^&* (zoals gevraagd)
    characters = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(characters) for _ in range(length))


# --- Helper Functies ---

def ensure_indexes(db):
    """Zorgt ervoor dat de benodigde MongoDB-indexen bestaan en TTL wordt ingesteld. (Feature 7 & 8)"""
    try:
        # Index voor snelle statistieken en client filtering (timestamp en source)
        db['statistics'].create_index([("timestamp", 1), ("source", 1)], name="stats_time_source_index", background=True)
        
        # Feature 8: TTL Index voor automatische dataverwijdering na 365 dagen
        # 365 dagen * 24 uur * 60 min * 60 sec = 31,536,000 seconden
        db['statistics'].create_index("timestamp", expireAfterSeconds=31536000, name="ttl_365_days", background=True) 
        
        # Index voor snelle zoekopdrachten op de data
        db['app_data'].create_index([("source_app", 1), ("timestamp", -1)], name="data_source_time_index", background=True)
        
        # Feature 1: Indexen voor API Keys
        db['api_keys'].create_index("key", unique=True, name="key_unique_index", background=True)
        db['api_keys'].create_index("client_id", unique=True, name="client_id_unique_index", background=True)
        
        # --- NIEUW VOOR CLOUD SYNC ---
        # Zorgt ervoor dat item_id uniek is per gebruiker (source_app) in de actieve staat
        db['active_state'].create_index([("source_app", 1), ("item_id", 1)], unique=True, name="unique_item_per_user", background=True)
        
        print("MongoDB Indexen gecontroleerd en aangemaakt.")
    except Exception as e:
        print(f"Waarschuwing: Index aanmaken mislukt: {e}")

def get_db_connection(uri=None):
    """Hergebruikt de globale connectie of maakt deze aan. (Feature 5)"""
    global MONGO_CLIENT
    target_uri = uri if uri else app.config.get('MONGO_URI')

    if not target_uri:
        return None, "MongoDB URI is niet geconfigureerd."

    # Probeer client opnieuw te initialiseren als deze None is (eerste keer of reset)
    if MONGO_CLIENT is None or uri is not None:
        try:
            # Maak een nieuwe connectie
            client = MongoClient(target_uri, serverSelectionTimeoutMS=5000)
            client.admin.command('ping') # Test verbinding
            
            # Update de globale client als dit geen test-URI is
            if uri is None:
                MONGO_CLIENT = client
            else: # Als het een test URI is, gebruik de tijdelijke client voor indexen
                db = client['api_gateway_db']
                ensure_indexes(db)
                return client, None
            
            # Zorg voor indexen
            db = MONGO_CLIENT['api_gateway_db']
            ensure_indexes(db)
            
            return MONGO_CLIENT, None
        except ConnectionFailure:
            return None, "Kon geen verbinding maken met de MongoDB-server."
        except OperationFailure as e:
            return None, f"Authenticatie of Operationele Fout: {e}"
        except Exception as e:
            return None, f"Onbekende fout: {e}"
            
    # Gebruik de reeds bestaande globale client
    try:
        MONGO_CLIENT.admin.command('ping') # Test of de verbinding nog actief is
        return MONGO_CLIENT, None
    except Exception as e:
        # Connectie verloren, reset globale client en meld fout
        MONGO_CLIENT = None
        return None, f"Verbinding verloren: {e}"

def log_statistic(action, source_app):
    """Logt een actie naar de MongoDB database voor statistieken."""
    client, _ = get_db_connection()
    if client:
        try:
            db = client['api_gateway_db']
            stats = db['statistics']
            stats.insert_one({
                'timestamp': datetime.datetime.utcnow(),
                'action': action,
                'source': source_app
            })
        except Exception as e:
            # Print foutmelding, maar laat de API call niet falen
            print(f"Fout bij loggen van statistiek: {e}")

# --- Database Key Management (Feature 1) ---

def load_api_keys():
    """Laadt alle actieve sleutels uit de database. (Feature 1)"""
    client, error = get_db_connection()
    if not client:
        return {}
    
    db = client['api_gateway_db']
    keys_cursor = db['api_keys'].find({})
    
    # Maak een dictionary {client_id: {'key': key, 'description': desc}}
    keys = {}
    for doc in keys_cursor:
        keys[doc['client_id']] = {
            'key': doc['key'],
            'description': doc['description']
        }
    return keys

def save_new_api_key(client_id, key, description):
    """Slaat een nieuwe sleutel op in de database. (Feature 1)"""
    client, error = get_db_connection()
    if not client:
        return False, "Database niet verbonden."
    
    db = client['api_gateway_db']
    try:
        db['api_keys'].insert_one({
            'client_id': client_id,
            'key': key,
            'description': description,
            'created_at': datetime.datetime.utcnow()
        })
        return True, None
    except Exception as e:
        return False, str(e)

def revoke_api_key_db(client_id):
    """Trekt een sleutel in door deze uit de database te verwijderen. (Feature 1)"""
    client, error = get_db_connection()
    if not client:
        return False, "Database niet verbonden."
    
    db = client['api_gateway_db']
    try:
        result = db['api_keys'].delete_one({'client_id': client_id})
        return result.deleted_count > 0, None
    except Exception as e:
        return False, str(e)

# --- INITIALISATIE ---
app = Flask(__name__)
# Voeg CORS toe: Staat alle origins toe om de API-endpoints te benaderen.
CORS(app) 
app.config['MONGO_URI'] = DEFAULT_MONGO_URI # Plaats config hier

# Functie om de client te identificeren voor Rate Limiting (Feature 6)
def get_client_id():
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        
        # Zoek in de database naar de token (Feature 1)
        client, _ = get_db_connection()
        if client:
            db = client['api_gateway_db']
            key_doc = db['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc:
                return key_doc['client_id']
                
    # Val terug op IP-adres als er geen geldige token is
    return get_remote_address()

# Initialiseer Limiter (Feature 6: Rate Limiting)
limiter = Limiter(
    key_func=get_client_id, 
    app=app, 
    default_limits=["1000 per day", "200 per hour"], # Iets ruimer gezet voor sync
    storage_uri="memory://" 
)

# Gebruik een veilige sleutel uit de omgeving, anders een standaardwaarde.
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-this')

# --- Authenticatie Decorator (Feature 1: API Key Validation) ---
def require_api_key(f):
    """Decorator om de API Key te valideren. (Feature 1)"""
    def wrapper(*args, **kwargs):
        # Allow OPTIONS requests for CORS preflight without authentication
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authenticatie vereist. Gebruik 'Authorization: Bearer <key>'"}), 401
        
        token = auth_header.split(' ')[1]
        
        # Zoek in de database (Feature 1)
        client, _ = get_db_connection()
        client_id = None
        if client:
            db = client['api_gateway_db']
            key_doc = db['api_keys'].find_one({'key': token}, {'client_id': 1})
            if key_doc:
                client_id = key_doc['client_id']
        
        if client_id:
            request.client_id = client_id
            return f(*args, **kwargs)
        else:
            return jsonify({"error": "Ongeldige API-sleutel"}), 401
    
    wrapper.__name__ = f.__name__ 
    return wrapper

# --- HTML TEMPLATES ---

# De basislayout bevat nu een placeholder voor de specifieke content
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
        body { background-color: #121212; color: #e0e0e0; }
        .card { background-color: #1e1e1e; border: 1px solid #333; margin-bottom: 20px; }
        .sidebar { min-height: 100vh; background-color: #191919; border-right: 1px solid #333; }
        .nav-link { color: #aaa; }
        .nav-link:hover, .nav-link.active { color: #fff; background-color: #333; border-radius: 5px; }
        .status-dot { height: 12px; width: 12px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .dot-green { background-color: #28a745; box-shadow: 0 0 5px #28a745; }
        .dot-red { background-color: #dc3545; box-shadow: 0 0 5px #dc3545; }
        .log-timestamp { white-space: nowrap; }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            <!-- Sidebar -->
            <nav class="col-md-3 col-lg-2 d-md-block sidebar collapse p-3">
                <h4 class="mb-4 text-white"><i class="bi bi-hdd-network"></i> Gateway</h4>
                <ul class="nav flex-column">
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if page == 'dashboard' else '' }}" href="/">
                            <i class="bi bi-speedometer2"></i> Dashboard
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if page == 'settings' else '' }}" href="/settings">
                            <i class="bi bi-gear"></i> Instellingen
                        </a>
                    </li>
                </ul>
                <div class="mt-auto pt-4 border-top border-secondary">
                    <small class="text-muted">Versie 1.1.0 (Cloud Sync)</small>
                </div>
            </nav>

            <!-- Main Content: HIER WORDT DE CONTENT GEÏNJECTEERD -->
            <main class="col-md-9 ms-sm-auto col-lg-10 px-md-4 py-4">
                {% with messages = get_flashed_messages(with_categories=true) %}
                  {% if messages %}
                    {% for category, message in messages %}
                      <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                      </div>
                    {% endfor %}
                  {% endif %}
                {% endwith %}
                
                {{ page_content | safe }}

            </main>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <!-- Feature 10: Tijdzone Conversie -->
    <script>
        function convertUtcToLocal() {
            document.querySelectorAll('.utc-timestamp').forEach(element => {
                const utcTime = element.dataset.utc;
                if (utcTime) {
                    const date = new Date(utcTime + 'Z'); // Z (Zulu) geeft aan dat het UTC is
                    // Controleer of de conversie geldig is voordat deze wordt weergegeven
                    if (!isNaN(date)) {
                        element.textContent = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
                    } else {
                         element.textContent = 'Ongeldige tijd';
                    }
                    element.classList.remove('utc-timestamp'); // Voorkom dubbele conversie
                }
            });
        }

        // Zorg ervoor dat de functie wordt uitgevoerd wanneer de DOM geladen is
        convertUtcToLocal();

        {% if page == 'dashboard' %}
        // Feature 4: Real-time Dashboard Statistieken (Chart.js)
        // De JSON data wordt hier uit de verborgen script tag geladen
        const chartData = JSON.parse(document.getElementById('chart-data').textContent);
        
        const ctx = document.getElementById('activityChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: 'API Requests',
                    data: chartData.counts,
                    backgroundColor: 'rgba(13, 110, 253, 0.6)',
                    borderColor: '#0d6efd',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: { 
                        beginAtZero: true, 
                        grid: { color: '#333' },
                        ticks: { color: '#aaa', precision: 0 }
                    },
                    x: { 
                        grid: { color: '#333' },
                        ticks: { color: '#aaa' }
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: '#aaa' }
                    }
                }
            }
        });
        {% endif %}
    </script>
</body>
</html>
"""

# Dashboard Content 
DASHBOARD_CONTENT = """
    <h2 class="mb-4">Systeem Status</h2>
    
    <!-- Status Cards -->
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card p-3">
                <h5 class="card-title text-muted">MongoDB</h5>
                <div class="d-flex align-items-center mt-2">
                    {% if db_connected %}
                        <span class="status-dot dot-green"></span> <h4 class="m-0">Verbonden</h4>
                    {% else %}
                        <span class="status-dot dot-red"></span> <h4 class="m-0">Fout</h4>
                    {% endif %}
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3">
                <h5 class="card-title text-muted">Totaal Logs (24u)</h5>
                <h3 class="mt-2">{{ stats_count }}</h3>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3">
                <h5 class="card-title text-muted">Actieve Clients</h5>
                <h3 class="mt-2">{{ client_count }}</h3>
            </div>
        </div>
         <div class="col-md-3">
            <div class="card p-3 border-info">
                <h5 class="card-title text-info">Cloud Items</h5>
                <h3 class="mt-2">{{ synced_items_count }}</h3>
                <small class="text-muted">Actueel opgeslagen</small>
            </div>
        </div>
    </div>

    <!-- Charts & Tables -->
    <div class="row">
        <div class="col-md-8">
            <div class="card p-3">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="card-title m-0">Recente Activiteit</h5>
                    <!-- Nieuwe filter dropdown -->
                    <div class="dropdown">
                        <button class="btn btn-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                            Bereik: {{ current_range_label }}
                        </button>
                        <ul class="dropdown-menu dropdown-menu-dark">
                            <li><a class="dropdown-item {{ 'active' if time_range == '6h' else '' }}" href="{{ url_for('dashboard', range='6h') }}">Laatste 6 uur</a></li>
                            <li><a class="dropdown-item {{ 'active' if time_range == '24h' else '' }}" href="{{ url_for('dashboard', range='24h') }}">Laatste 24 uur</a></li>
                            <li><a class="dropdown-item {{ 'active' if time_range == '7d' else '' }}" href="{{ url_for('dashboard', range='7d') }}">Laatste Week (7 dagen)</a></li>
                            <li><a class="dropdown-item {{ 'active' if time_range == '30d' else '' }}" href="{{ url_for('dashboard', range='30d') }}">Laatste Maand (30 dagen)</a></li>
                            <li><a class="dropdown-item {{ 'active' if time_range == '365d' else '' }}" href="{{ url_for('dashboard', range='365d') }}">Laatste Jaar (365 dagen)</a></li>
                        </ul>
                    </div>
                </div>
                
                <!-- Feature 4: Verborgen JSON data voor de Chart -->
                <script id="chart-data" type="application/json">
                    {{ chart_data | tojson | safe }}
                </script>
                <canvas id="activityChart" height="100"></canvas>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card p-3">
                <h5 class="card-title">Geregistreerde Clients (24u)</h5>
                <ul class="list-group list-group-flush mt-3">
                    {% for client in clients %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between align-items-center">
                        <!-- Feature 9: Link naar detail view -->
                        <a href="{{ url_for('client_detail', source_app=client) }}" class="text-decoration-none text-info hover:text-white">
                            {{ client }}
                        </a>
                        <span class="badge bg-primary rounded-pill">Actief</span>
                    </li>
                    {% else %}
                    <li class="list-group-item bg-transparent text-muted">Geen clients gedetecteerd</li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>
"""

# Client Detail Content (Feature 9)
CLIENT_DETAIL_CONTENT = """
    <h2 class="mb-4">Client Detail: <span class="text-info">{{ source_app }}</span></h2>
    <a href="/" class="btn btn-sm btn-secondary mb-4"><i class="bi bi-arrow-left"></i> Terug naar Dashboard</a>

    <!-- Client Info Card -->
    <div class="card p-4 mb-4">
        <h5 class="card-title mb-3">Client Informatie</h5>
        <p><strong>Laatste 24u Requests:</strong> <span class="badge bg-primary">{{ total_requests }}</span></p>
        <p><strong>Toegestane API Sleutel:</strong> 
            {% if api_key_length > 0 %}
                <span class="badge bg-success">*** ({{ api_key_length }} tekens)</span>
            {% else %}
                <span class="badge bg-danger">Geen sleutel gevonden</span>
            {% endif %}
        </p>
        <p><strong>Rate Limit:</strong> 200 per uur / 1000 per dag</p>
    </div>

    <!-- Latest Data Logs -->
    <div class="card p-4">
        <h5 class="card-title mb-3">Laatste 10 Data Logboek regels</h5>
        
        <table class="table table-dark table-striped table-hover">
            <thead>
                <tr>
                    <th scope="col">Tijdstempel (Lokaal)</th>
                    <th scope="col">Actie</th>
                    <th scope="col">Payload Fragment</th>
                </tr>
            </thead>
            <tbody>
                {% for log in logs %}
                <tr>
                    <td class="log-timestamp utc-timestamp" data-utc="{{ log.timestamp }}"></td>
                    <td>{{ log.action }}</td>
                    <td><pre class="m-0 p-0 bg-transparent text-white small">{{ log.payload }}</pre></td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="3" class="text-center text-muted">Geen recente logboeken gevonden voor deze client.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
"""

# Settings Content
SETTINGS_CONTENT = """
    <h2 class="mb-4">Instellingen</h2>
    
    <div class="row">
        <div class="col-md-6">
            <div class="card p-4">
                <h5 class="card-title mb-3">Database Configuratie</h5>
                <form method="POST" action="/settings">
                    <div class="mb-3">
                        <label for="mongo_uri" class="form-label">MongoDB Connection URI</label>
                        <input type="text" class="form-control bg-dark text-white border-secondary" 
                               id="mongo_uri" name="mongo_uri" value="{{ current_uri }}">
                        <div class="form-text text-muted">Voorbeeld: mongodb://gebruiker:wachtwoord@host:27017/</div>
                    </div>
                    <button type="submit" name="action" value="save" class="btn btn-primary">Opslaan</button>
                    <button type="submit" name="action" value="test" class="btn btn-warning ms-2">
                        <i class="bi bi-lightning-fill"></i> Test Verbinding
                    </button>
                </form>
            </div>

            <!-- Nieuwe Sectie: API Sleutel Generatie -->
            <div class="card p-4 mt-4">
                <h5 class="card-title mb-3">API Sleutel Generatie</h5>
                <p class="text-muted small">Genereer een nieuwe, unieke API-sleutel (20 tekens) voor een client. De sleutel wordt **éénmalig** getoond in een melding.</p>
                <form method="POST" action="/settings">
                    <div class="mb-3">
                        <label for="key_description" class="form-label">Omschrijving Client</label>
                        <input type="text" class="form-control bg-dark text-white border-secondary" 
                               id="key_description" name="key_description" required placeholder="Bijv. Webshop Backend V2">
                    </div>
                    <button type="submit" name="action" value="generate_key" class="btn btn-success">
                        <i class="bi bi-key"></i> Genereer API Sleutel
                    </button>
                </form>
            </div>
            
            <!-- NIEUWE SECTIE: Eénmalige Sleutelweergave -->
            {% if new_key %}
            <div class="card p-4 mt-4 border-success">
                <h5 class="card-title text-success mb-3">Nieuwe Sleutel Succesvol Aangemaakt</h5>
                <p class="text-muted small">Sleutel voor **{{ new_key_desc }}** (ID: {{ new_key_id }}). Kopieer deze nu, want hij wordt niet meer getoond.</p>
                
                <div class="input-group mb-3">
                    <input type="text" class="form-control bg-dark text-success font-monospace" value="{{ new_key }}" id="generatedKey" readonly>
                    <button class="btn btn-outline-success" type="button" onclick="copyToClipboard('generatedKey', this)">
                        <i class="bi bi-clipboard"></i> Kopiëren
                    </button>
                </div>
            </div>
            <script>
                // Functie voor Kopiëren naar Klembord (gebruikt document.execCommand)
                function copyToClipboard(elementId, button) {
                    var copyText = document.getElementById(elementId);
                    
                    // Selecteer de tekst
                    copyText.select();
                    copyText.setSelectionRange(0, 99999); // Voor mobiel

                    // Kopieer de tekst
                    document.execCommand('copy');
                    
                    // Visuele feedback
                    button.innerHTML = '<i class="bi bi-check2"></i> Gekopieerd!';
                    setTimeout(() => {
                        button.innerHTML = '<i class="bi bi-clipboard"></i> Kopiëren';
                    }, 2000);
                }
            </script>
            {% endif %}
        </div>
        
        <div class="col-md-6">
            <div class="card p-4">
                <h5 class="card-title mb-3">Actieve API Sleutels</h5>
                <p>Deze sleutels worden gebruikt om verkeer te authenticeren en te limiteren.</p>
                <div class="alert alert-info small">
                    <strong>Opmerking:</strong> Sleutels worden permanent opgeslagen in de MongoDB-database.
                </div>
                <ul class="list-group">
                    {% for id, data in api_keys.items() %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between align-items-center">
                        <div>
                            <strong>{{ data.description }}:</strong> 
                            <span class="text-muted small">({{ id }})</span>
                        </div>
                        
                        <div class="d-flex align-items-center">
                             <!-- Sleutel wordt gemaskeerd -->
                            <code class="me-3">*** ({{ data.key | length }} tekens)</code>
                            
                            <!-- Revoke Formulier -->
                            <form method="POST" action="{{ url_for('settings') }}" onsubmit="return confirm('Weet u zeker dat u sleutel {{ id }} wilt intrekken? Dit is niet omkeerbaar!');">
                                <input type="hidden" name="action" value="revoke_key">
                                <input type="hidden" name="client_id" value="{{ id }}">
                                <button type="submit" class="btn btn-sm btn-danger">
                                    <i class="bi bi-trash"></i> Intrekken
                                </button>
                            </form>
                        </div>
                    </li>
                    {% else %}
                    <li class="list-group-item bg-transparent text-muted">Geen actieve sleutels. Gebruik de generator.</li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>
"""

# --- Routes ---

@app.route('/')
def dashboard():
    # Nieuwe logica voor tijdfilter:
    time_range = request.args.get('range', '6h') # Standaard naar 6 uur
    
    range_map = {
        '6h': {'delta': datetime.timedelta(hours=6), 'label': 'Laatste 6 uur', 'group': '%H:00', 'fill_interval': 'hour'},
        '24h': {'delta': datetime.timedelta(hours=24), 'label': 'Laatste 24 uur', 'group': '%H:00', 'fill_interval': 'hour'},
        '7d': {'delta': datetime.timedelta(days=7), 'label': 'Laatste Week', 'group': '%a %d', 'fill_interval': 'day'}, # Dag van de week
        '30d': {'delta': datetime.timedelta(days=30), 'label': 'Laatste Maand', 'group': '%d %b', 'fill_interval': 'day'}, # Dag en maand
        '365d': {'delta': datetime.timedelta(days=365), 'label': 'Laatste Jaar', 'group': '%b %Y', 'fill_interval': 'month'}, # Maand en jaar
    }
    
    current_range = range_map.get(time_range, range_map['6h'])
    delta = current_range['delta']
    start_time = datetime.datetime.utcnow() - delta
    
    # --- MongoDB Connectie en Basis Statistieken ---
    client, error = get_db_connection()
    db_connected = client is not None
    
    stats_count = 0
    synced_items_count = 0 # NIEUW
    unique_clients = []
    chart_data = {"labels": [], "counts": []}

    if db_connected:
        try:
            db = client['api_gateway_db']
            
            # --- Basis Statistieken (altijd op 24u) ---
            yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            stats_count = db['statistics'].count_documents({'timestamp': {'$gte': yesterday}})
            
            # NIEUW: Tel hoeveel actieve items er in de cloud staan
            synced_items_count = db['active_state'].count_documents({})
            
            unique_clients = db['statistics'].distinct('source', {'timestamp': {'$gte': yesterday}})
            
            # --- Feature: Dynamische Grafiek Data (Gebaseerd op geselecteerde range) ---
            
            # 1. MongoDB Aggregation Pipeline
            pipeline = [
                {'$match': {'timestamp': {'$gte': start_time}}},
                {'$group': {
                    '_id': {'$dateToString': {'format': current_range['group'], 'date': '$timestamp'}}, 
                    'count': {'$sum': 1},
                    'latest_time': {'$max': '$timestamp'}
                }},
                {'$sort': {'latest_time': 1}}
            ]
            aggregated_counts = list(db['statistics'].aggregate(pipeline))
            
            # Converteer aggregation resultaat naar een dictionary voor sneller zoeken
            agg_dict = {item['_id']: item['count'] for item in aggregated_counts}

            # 2. Label Generatie en Data Vulling (vult gaten op waar count = 0)
            chart_labels = []
            chart_counts = []
            current = start_time
            now = datetime.datetime.utcnow()

            # Bepaal hoe te itereren (uur, dag, maand)
            if current_range['fill_interval'] == 'hour':
                while current < now:
                    label = current.strftime('%H:00')
                    chart_labels.append(label)
                    chart_counts.append(agg_dict.get(label, 0))
                    current += datetime.timedelta(hours=1)
            elif current_range['fill_interval'] == 'day':
                while current < now:
                    label = current.strftime(current_range['group'])
                    chart_labels.append(label)
                    chart_counts.append(agg_dict.get(label, 0))
                    current += datetime.timedelta(days=1)
            elif current_range['fill_interval'] == 'month':
                # Gebruik start van de maand voor correcte labels
                current = datetime.datetime(current.year, current.month, 1)
                
                while current < now:
                    label = current.strftime(current_range['group'])
                    chart_labels.append(label)
                    chart_counts.append(agg_dict.get(label, 0))
                    
                    # Ga naar de volgende maand
                    next_month = current.month + 1
                    next_year = current.year
                    if next_month > 12:
                        next_month = 1
                        next_year += 1
                    current = datetime.datetime(next_year, next_month, 1)
            
            chart_data = {"labels": chart_labels, "counts": chart_counts}
            
        except Exception:
            pass
    
    # Eerst de specifieke inhoud renderen met de benodigde variabelen
    rendered_content = render_template_string(DASHBOARD_CONTENT,
                                            db_connected=db_connected,
                                            db_uri=app.config['MONGO_URI'],
                                            stats_count=stats_count,
                                            synced_items_count=synced_items_count, # NIEUW DOORGEVEN AAN TEMPLATE
                                            client_count=len(unique_clients),
                                            clients=unique_clients,
                                            chart_data=chart_data,
                                            time_range=time_range, 
                                            current_range_label=current_range['label']) 
            
    # Vervolgens de basislayout renderen, inclusief de zojuist gerenderde inhoud
    return render_template_string(BASE_LAYOUT, 
                                  page='dashboard',
                                  page_content=rendered_content)


@app.route('/client/<source_app>')
def client_detail(source_app):
    """Toont gedetailleerde logboeken voor een specifieke client. (Feature 9)"""
    client, error = get_db_connection()
    logs = []
    total_requests = 0
    api_key_length = 0
    
    # Zoek de API key lengte voor weergave (Feature 1: Lezen uit DB)
    api_keys_db = load_api_keys()
    api_key_data = api_keys_db.get(source_app)
    if api_key_data:
        api_key_length = len(api_key_data['key'])

    if client:
        try:
            db = client['api_gateway_db']
            
            # Totaal requests (24u)
            yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            total_requests = db['statistics'].count_documents({
                'source': source_app,
                'timestamp': {'$gte': yesterday}
            })
            
            # Haal de laatste 10 logs op van de app_data collectie
            cursor = db['app_data'].find({'source_app': source_app}).sort('timestamp', -1).limit(10)
            
            for doc in cursor:
                # Beperk de payload voor overzichtelijkheid
                payload_str = json.dumps(doc.get('payload', {}), indent=2)
                if len(payload_str) > 100:
                    payload_str = payload_str[:100] + '...'
                
                # Bepaal actie type
                action_type = doc.get('action', 'Data Post')
                if doc.get('payload') and isinstance(doc.get('payload'), dict):
                     action_type = doc.get('payload').get('action', action_type)
                    
                logs.append({
                    'timestamp': doc['timestamp'].isoformat(), # Feature 10: Tijdstempel als ISO string voor JS
                    'action': action_type,
                    'payload': payload_str
                })
        except Exception as e:
            flash(f'Fout bij het ophalen van clientdetails: {e}', 'danger')

    rendered_content = render_template_string(CLIENT_DETAIL_CONTENT,
                                            source_app=source_app,
                                            total_requests=total_requests,
                                            api_key_length=api_key_length,
                                            logs=logs)
    
    return render_template_string(BASE_LAYOUT, 
                                  page='client_detail', 
                                  page_content=rendered_content)


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'generate_key':
            description = request.form.get('key_description', 'Nieuwe client')
            new_key = generate_random_key(20)
            
            # Creëer een unieke client ID
            base_name = description.replace(' ', '_').replace('-', '_').replace('.', '').lower()
            i = 1
            client_id = base_name
            
            # Controleer op unieke client ID in de database (Feature 1)
            keys_db = load_api_keys()
            while client_id in keys_db:
                client_id = f"{base_name}_{i}"
                i += 1

            # Sla de nieuwe sleutel op in de database (Feature 1)
            success, db_error = save_new_api_key(client_id, new_key, description)

            if success:
                # Sla de key en description op in de session voor eenmalige weergave
                session['new_key'] = new_key
                session['new_key_desc'] = description
                session['new_key_id'] = client_id
                
                flash(f'Sleutel voor "{description}" is gegenereerd en wordt nu éénmalig getoond.', 'success')
            else:
                flash(f'Fout bij het genereren van de sleutel: {db_error}', 'danger')
            
            return redirect(url_for('settings'))
            
        elif action == 'revoke_key':
            client_id_to_revoke = request.form.get('client_id')
            
            # Verwijder de sleutel uit de database (Feature 1)
            success, db_error = revoke_api_key_db(client_id_to_revoke)

            if success:
                flash(f'API-sleutel voor "{client_id_to_revoke}" is succesvol ingetrokken en verwijderd.', 'warning')
            else:
                flash(f'Fout bij het intrekken van de sleutel: {db_error}', 'danger')
            return redirect(url_for('settings'))

        # Logica voor opslaan/testen database URI
        new_uri = request.form.get('mongo_uri')
        
        if new_uri:
            app.config['MONGO_URI'] = new_uri
        
        if action == 'test':
            # Gebruik de tijdelijke client (uri is niet None)
            client, error = get_db_connection(app.config['MONGO_URI']) 
            if client:
                flash('Verbinding succesvol! Database is bereikbaar.', 'success')
            else:
                # Toon de gedetailleerde fout in de flash message
                flash(f'Verbinding mislukt: {error}', 'danger')
        elif action == 'save':
            # Probeer de globale client bij te werken (Feature 5)
            client, error = get_db_connection(None) 
            if client:
                flash('Instellingen opgeslagen. Globale verbinding bijgewerkt.', 'info')
            else:
                flash(f'Instellingen opgeslagen, maar kon geen nieuwe globale verbinding maken: {error}', 'danger')
            
    # Laad sleutels uit DB voor weergave (Feature 1)
    active_api_keys = load_api_keys() 
    
    # Haal éénmalige sleutel op uit session (en wis deze)
    new_key = session.pop('new_key', None)
    new_key_desc = session.pop('new_key_desc', None)
    new_key_id = session.pop('new_key_id', None)
            
    # Eerst de specifieke inhoud renderen met de benodigde variabelen
    rendered_content = render_template_string(SETTINGS_CONTENT,
                                            current_uri=app.config['MONGO_URI'],
                                            env_host=os.environ.get('HOSTNAME', 'Unknown'),
                                            api_keys=active_api_keys,
                                            new_key=new_key, # Wordt alleen gerenderd als deze in session stond
                                            new_key_desc=new_key_desc,
                                            new_key_id=new_key_id) 
    
    # Vervolgens de basislayout renderen, inclusief de zojuist gerenderde inhoud
    return render_template_string(BASE_LAYOUT, 
                                  page='settings', 
                                  page_content=rendered_content)

# --- API Endpoints voor externe Apps ---

@app.route('/api/health', methods=['GET']) 
def health_check():
    """Simple health check endpoint."""
    client, error = get_db_connection()
    db_status = "ok" if client else "error"
    return jsonify({
        "status": "running", 
        "service": "API Gateway",
        "mongodb_status": db_status
    })

@app.route('/api/data', methods=['GET', 'POST', 'OPTIONS']) # AANGEPAST: GET & OPTIONS toegevoegd
@require_api_key # Feature 1: Vereist een geldige Bearer Token
@limiter.limit("50 per hour") 
@limiter.limit("200 per day") 
def handle_data():
    """
    Endpoint voor data synchronisatie.
    GET: Haalt actuele staat op.
    POST: Slaat updates op (logt historie EN update actuele staat).
    """
    # Gebruik de gevalideerde client ID uit de request context
    source_app = getattr(request, 'client_id', 'unknown_client')
    
    client, error = get_db_connection()
    if not client:
        # Als database down is, reageer met 503 Service Unavailable
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
            
            # STAP A: Altijd loggen naar de historie (Audit Trail) - BEHOUDEN VAN ORIGINEEL
            db['app_data'].insert_one({
                'timestamp': datetime.datetime.utcnow(),
                'source_app': source_app,
                'action': action,
                'payload': payload # Sla de volledige payload op
            })
            
            # STAP B: Update de 'Active State' (De Cloud Database) - NIEUW
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
            
            # Log statistiek
            log_statistic('sync_upload', source_app)
            
            return jsonify({"status": "success", "message": "Data processed", "client": source_app, "action": action}), 201

        except Exception as e:
            log_statistic('db_write_error', source_app)
            return jsonify({"error": f"Failed to write data to database: {str(e)}"}), 500

if __name__ == '__main__':
    # Initialiseer de globale connectie pool bij het opstarten
    get_db_connection() 
    # Luister op 0.0.0.0 om bereikbaar te zijn van buiten de container
    app.run(host='0.0.0.0', port=5000, debug=True)
