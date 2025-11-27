import os
import datetime
import json
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash
# Nieuwe import voor CORS-ondersteuning
from flask_cors import CORS 
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# --- INITIALISATIE ---
app = Flask(__name__)
# Voeg CORS toe: Staat alle origins toe om de API-endpoints te benaderen.
CORS(app) 
# Gebruik een veilige sleutel uit de omgeving, anders een standaardwaarde.
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-this')

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
app.config['MONGO_URI'] = DEFAULT_MONGO_URI

# --- Helper Functies ---
def get_db_connection(uri=None):
    """Probeert verbinding te maken met MongoDB."""
    target_uri = uri if uri else app.config.get('MONGO_URI')
    
    if not target_uri:
        return None, "MongoDB URI is niet geconfigureerd."

    try:
        # VERHOOGD: 2000ms naar 5000ms voor meer tolerantie bij netwerklatentie
        client = MongoClient(target_uri, serverSelectionTimeoutMS=5000)
        # Check of de server beschikbaar is door een commando uit te voeren
        client.admin.command('ping')
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

# --- HTML TEMPLATES (Gecorrigeerde Structuur) ---

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
    {% if page == 'dashboard' %}
    <script>
        // Simpele dummy chart data, in het echt zou dit uit de backend komen
        const ctx = document.getElementById('activityChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['10:00', '11:00', '12:00', '13:00', '14:00', '15:00'],
                datasets: [{
                    label: 'API Requests',
                    data: [12, 19, 3, 5, 2, 3],
                    borderColor: '#0d6efd',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        labels: { color: '#aaa' }
                    }
                },
                scales: {
                    y: { 
                        beginAtZero: true, 
                        grid: { color: '#333' },
                        ticks: { color: '#aaa' }
                    },
                    x: { 
                        grid: { color: '#333' },
                        ticks: { color: '#aaa' }
                    }
                }
            }
        });
    </script>
    {% endif %}
</body>
</html>
"""

# Dashboard Content (bevat GEEN base layout of block tags meer)
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
                <h5 class="card-title">Recente Activiteit</h5>
                <canvas id="activityChart" height="100"></canvas>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card p-3">
                <h5 class="card-title">Geregistreerde Clients</h5>
                <ul class="list-group list-group-flush mt-3">
                    {% for client in clients %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between align-items-center">
                        {{ client }}
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

# Settings Content (bevat GEEN base layout of block tags meer)
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
                <h5 class="card-title mb-3">Debug Informatie</h5>
                <p>Environment Variables:</p>
                <pre class="bg-dark p-2 border border-secondary rounded">HOSTNAME: {{ env_host }}</pre>
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

    if db_connected:
        try:
            db = client['api_gateway_db']
            # Haal statistieken op (bijv. aantal docs in stats collectie)
            stats_count = db['statistics'].count_documents({})
            # Haal unieke 'source' velden op voor client lijst
            # Filter op clients die in de afgelopen 24 uur actief waren
            yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            unique_clients = db['statistics'].distinct('source', {'timestamp': {'$gte': yesterday}})
        except Exception:
            pass
    
    # Eerst de specifieke inhoud renderen met de benodigde variabelen
    rendered_content = render_template_string(DASHBOARD_CONTENT,
                                            db_connected=db_connected,
                                            db_uri=app.config['MONGO_URI'],
                                            stats_count=stats_count,
                                            client_count=len(unique_clients),
                                            clients=unique_clients)
            
    # Vervolgens de basislayout renderen, inclusief de zojuist gerenderde inhoud
    return render_template_string(BASE_LAYOUT, 
                                  page='dashboard',
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
                                            env_host=os.environ.get('HOSTNAME', 'Unknown'))
    
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

@app.route('/api/data', methods=['POST'])
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

    source_app = data.get('source_app', 'unknown_client')
    
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
        
        return jsonify({"status": "success", "message": "Data processed"}), 201
    except Exception as e:
        log_statistic('db_write_error', source_app)
        return jsonify({"error": f"Failed to write data to database: {str(e)}"}), 500

if __name__ == '__main__':
    # Luister op 0.0.0.0 om bereikbaar te zijn van buiten de container
    app.run(host='0.0.0.0', port=5000, debug=True)
