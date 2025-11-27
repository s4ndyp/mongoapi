import os
import datetime
import json
import secrets # Voor API Key authenticatie
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, abort
from flask_cors import CORS 
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from flask_limiter import Limiter # Voor Rate Limiting (Feature 6)
from flask_limiter.util import get_remote_address # Nodig voor Limiter

# --- STATIC API KEYS (Feature 1: Authenticatie) ---
# In een echte app zouden deze uit een database of HashiCorp Vault komen.
# Gebruik de source_app naam als API key ID.
API_KEYS = {
    "Webshop_Kassa_1": "KASSA_SECRET_12345", 
    "Mobiele_App_2": "MOB_APP_SECRET_67890"
}
# Functie om de client te identificeren voor Rate Limiting (Feature 6)
def get_client_id():
    # Probeer de API key (Authorization header) te gebruiken voor Rate Limiting
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        for client_id, key in API_KEYS.items():
            if token == key:
                return client_id
    # Val terug op IP-adres als er geen geldige token is
    return get_remote_address()


# --- INITIALISATIE ---
app = Flask(__name__)
# Voeg CORS toe: Staat alle origins toe om de API-endpoints te benaderen.
CORS(app) 
# Initialiseer Limiter (Feature 6: Rate Limiting)
# Gebruikt de 'get_client_id' functie om de client te identificeren
limiter = Limiter(
    key_func=get_client_id, 
    app=app, 
    default_limits=["200 per day", "50 per hour"], # Standaardlimieten
    storage_uri="memory://" # Gebruik geheugen voor eenvoud
)

# Gebruik een veilige sleutel uit de omgeving, anders een standaardwaarde.
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-this')

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
app.config['MONGO_URI'] = DEFAULT_MONGO_URI


# --- Helper Functies ---

def ensure_indexes(db):
    """Zorgt ervoor dat de benodigde MongoDB-indexen bestaan. (Feature 7)"""
    try:
        # Index voor snelle statistieken en client filtering (timestamp en source)
        db['statistics'].create_index([("timestamp", 1), ("source", 1)], name="stats_time_source_index", background=True)
        # Index voor snelle zoekopdrachten op de data
        db['app_data'].create_index([("source_app", 1), ("timestamp", -1)], name="data_source_time_index", background=True)
        print("MongoDB Indexen gecontroleerd en aangemaakt.")
    except Exception as e:
        print(f"Waarschuwing: Index aanmaken mislukt: {e}")

def get_db_connection(uri=None):
    """Probeert verbinding te maken met MongoDB en zorgt voor indexen."""
    target_uri = uri if uri else app.config.get('MONGO_URI')
    
    if not target_uri:
        return None, "MongoDB URI is niet geconfigureerd."

    try:
        # VERHOOGD: 2000ms naar 5000ms voor meer tolerantie bij netwerklatentie
        client = MongoClient(target_uri, serverSelectionTimeoutMS=5000)
        # Check of de server beschikbaar is door een commando uit te voeren
        client.admin.command('ping')
        
        # Zorgt voor indexen direct na succesvolle verbinding (Feature 7)
        db = client['api_gateway_db']
        ensure_indexes(db)
        
        return client, None
    except ConnectionFailure:
        return None, "Kon geen verbinding maken met de MongoDB-server."
    except OperationFailure as e:
        return None, f"Authenticatie of Operationele Fout: {e}"
    except Exception as e:
        return None, f"Onbekende fout: {e}"

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

# --- Authenticatie Decorator (Feature 1: API Key Validation) ---
def require_api_key(f):
    """Decorator om de API Key te valideren."""
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authenticatie vereist. Gebruik 'Authorization: Bearer <key>'"}), 401
        
        token = auth_header.split(' ')[1]
        
        # Zoek de client_id die overeenkomt met de token
        client_id = next((c for c, key in API_KEYS.items() if key == token), None)
        
        if client_id:
            # Sla de client_id op in de request context voor logging/rate limiting
            request.client_id = client_id
            return f(*args, **kwargs)
        else:
            return jsonify({"error": "Ongeldige API-sleutel"}), 401
    
    wrapper.__name__ = f.__name__ # Nodig voor Flask
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
                    <small class="text-muted">Versie 1.0.0 (Docker)</small>
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
                    label: 'API Requests per Uur',
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
        <div class="col-md-4">
            <div class="card p-3">
                <h5 class="card-title text-muted">MongoDB Connectie</h5>
                <div class="d-flex align-items-center mt-2">
                    {% if db_connected %}
                        <span class="status-dot dot-green"></span> <h3 class="m-0">Verbonden</h3>
                    {% else %}
                        <span class="status-dot dot-red"></span> <h3 class="m-0">Fout</h3>
                    {% endif %}
                </div>
                <small class="text-muted mt-2">{{ db_uri }}</small>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card p-3">
                <h5 class="card-title text-muted">Totaal Requests (24u)</h5>
                <h3 class="mt-2">{{ stats_count }}</h3>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card p-3">
                <h5 class="card-title text-muted">Actieve Clients</h5>
                <h3 class="mt-2">{{ client_count }}</h3>
            </div>
        </div>
    </div>

    <!-- Charts & Tables -->
    <div class="row">
        <div class="col-md-8">
            <div class="card p-3">
                <h5 class="card-title">Recente Activiteit (Laatste 6 uur)</h5>
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
            {% if api_key != 'N/A' %}
                <span class="badge bg-success">{{ api_key }}</span>
            {% else %}
                <span class="badge bg-danger">Geen sleutel gevonden</span>
            {% endif %}
        </p>
        <p><strong>Rate Limit:</strong> 50 per uur / 200 per dag (Feature 6)</p>
    </div>

    <!-- Latest Data Logs -->
    <div class="card p-4">
        <h5 class="card-title mb-3">Laatste 10 Data Posts</h5>
        
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
        </div>
        
        <div class="col-md-6">
            <div class="card p-4">
                <h5 class="card-title mb-3">API Sleutels</h5>
                <p>Ondersteunde API Sleutels voor authenticatie:</p>
                <ul class="list-group">
                    {% for id, key in api_keys.items() %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between">
                        <strong>{{ id }}:</strong> <code>{{ key }}</code>
                    </li>
                    {% endfor %}
                </ul>
                <div class="form-text text-muted mt-3">Gebruik deze sleutels in de 'Authorization: Bearer' header.</div>
            </div>
        </div>
    </div>
"""

# --- Routes ---

@app.route('/')
def dashboard():
    client, error = get_db_connection()
    db_connected = client is not None
    
    stats_count = 0
    unique_clients = []
    chart_data = {"labels": [], "counts": []}

    if db_connected:
        try:
            db = client['api_gateway_db']
            
            # --- Berekeningen voor Dashboard ---
            yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            
            # Totaal Requests (24u)
            stats_count = db['statistics'].count_documents({'timestamp': {'$gte': yesterday}})
            
            # Actieve Clients
            unique_clients = db['statistics'].distinct('source', {'timestamp': {'$gte': yesterday}})
            
            # Feature 4: Data voor Grafiek (Requests per uur over de laatste 6 uur)
            pipeline = [
                {'$match': {'timestamp': {'$gte': datetime.datetime.utcnow() - datetime.timedelta(hours=6)}}},
                {'$group': {
                    '_id': {'$hour': '$timestamp'}, 
                    'count': {'$sum': 1},
                    'latest_time': {'$max': '$timestamp'}
                }},
                {'$sort': {'latest_time': 1}}
            ]
            hourly_counts = list(db['statistics'].aggregate(pipeline))

            # Bereid de grafiekdata voor de laatste 6 uur voor
            chart_labels = []
            chart_counts = []
            now = datetime.datetime.utcnow()
            for i in range(6):
                hour_ago = now - datetime.timedelta(hours=6 - i)
                hour_label = hour_ago.strftime('%H:00')
                chart_labels.append(hour_label)
                
                # Zoek de telling voor dit uur
                found_count = next((item['count'] for item in hourly_counts if item['_id'] == hour_ago.hour), 0)
                chart_counts.append(found_count)
            
            chart_data = {"labels": chart_labels, "counts": chart_counts}
            
        except Exception:
            pass
    
    # Eerst de specifieke inhoud renderen met de benodigde variabelen
    rendered_content = render_template_string(DASHBOARD_CONTENT,
                                            db_connected=db_connected,
                                            db_uri=app.config['MONGO_URI'],
                                            stats_count=stats_count,
                                            client_count=len(unique_clients),
                                            clients=unique_clients,
                                            chart_data=chart_data) # Feature 4: Chart data toegevoegd
            
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
    
    # Zoek de API key voor weergave
    api_key = API_KEYS.get(source_app, "N/A")

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
                    
                logs.append({
                    'timestamp': doc['timestamp'].isoformat(), # Feature 10: Tijdstempel als ISO string voor JS
                    'action': 'Data Post',
                    'payload': payload_str
                })
        except Exception as e:
            flash(f'Fout bij het ophalen van clientdetails: {e}', 'danger')

    rendered_content = render_template_string(CLIENT_DETAIL_CONTENT,
                                            source_app=source_app,
                                            total_requests=total_requests,
                                            api_key=api_key,
                                            logs=logs)
    
    return render_template_string(BASE_LAYOUT, 
                                  page='client_detail', 
                                  page_content=rendered_content)


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        new_uri = request.form.get('mongo_uri')
        action = request.form.get('action')
        
        # Sla de nieuwe URI op in de configuratie
        app.config['MONGO_URI'] = new_uri
        
        if action == 'test':
            client, error = get_db_connection(new_uri)
            if client:
                flash('Verbinding succesvol! Database is bereikbaar.', 'success')
            else:
                # Toon de gedetailleerde fout in de flash message
                flash(f'Verbinding mislukt: {error}', 'danger')
        elif action == 'save':
            flash('Instellingen opgeslagen (sessie). Herstart container voor permanente wijziging.', 'info')
            
    # Eerst de specifieke inhoud renderen met de benodigde variabelen
    rendered_content = render_template_string(SETTINGS_CONTENT,
                                            current_uri=app.config['MONGO_URI'],
                                            env_host=os.environ.get('HOSTNAME', 'Unknown'),
                                            api_keys=API_KEYS) # API keys toegevoegd
    
    # Vervolgens de basislayout renderen, inclusief de zojuist gerenderde inhoud
    return render_template_string(BASE_LAYOUT, 
                                  page='settings', 
                                  page_content=rendered_content)

# --- API Endpoints voor externe Apps ---

@app.route('/api/health', methods=['GET']) # <-- Versie verwijderd
def health_check():
    """Simple health check endpoint."""
    client, error = get_db_connection()
    db_status = "ok" if client else "error"
    return jsonify({
        "status": "running", 
        "service": "API Gateway",
        "mongodb_status": db_status
    })

@app.route('/api/data', methods=['POST']) # <-- Versie verwijderd
@require_api_key # Feature 1: Vereist een geldige Bearer Token
@limiter.limit("50 per hour", override_key=get_client_id) # Feature 6: Rate Limiting
@limiter.limit("200 per day", override_key=get_client_id) # Feature 6: Tweede limiet
def handle_data():
    """
    Endpoint waar clients data naartoe sturen.
    Dit fungeert als proxy naar MongoDB.
    """
    try:
        data = request.json
    except Exception:
        return jsonify({"error": "Invalid JSON payload"}), 400
        
    if not data:
         return jsonify({"error": "Missing JSON data"}), 400

    # Gebruik de gevalideerde client ID uit de request context
    source_app = getattr(request, 'client_id', 'unknown_client')
    
    client, error = get_db_connection()
    if not client:
        # Als database down is, reageer met 503 Service Unavailable
        log_statistic('db_failed_request', source_app)
        return jsonify({"error": "Database not connected", "details": error}), 503
    
    try:
        db = client['api_gateway_db']
        # Sla de volledige inkomende JSON op
        db['app_data'].insert_one({
            'timestamp': datetime.datetime.utcnow(),
            'source_app': source_app,
            'payload': data # Sla de volledige payload op
        })
        
        # Log statistiek
        log_statistic('data_received', source_app)
        
        return jsonify({"status": "success", "message": "Data processed", "client": source_app}), 201
    except Exception as e:
        log_statistic('db_write_error', source_app)
        return jsonify({"error": f"Failed to write data to database: {str(e)}"}), 500

if __name__ == '__main__':
    # Luister op 0.0.0.0 om bereikbaar te zijn van buiten de container
    app.run(host='0.0.0.0', port=5000, debug=True)
