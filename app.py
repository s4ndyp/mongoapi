import os
import datetime
import json
import secrets
import time
import urllib.parse
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, flash
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from bson import ObjectId, json_util
import io
from flask import send_file

# Security Libraries
from bcrypt import hashpw, gensalt, checkpw

# TEMPLATES (Nu als strings in de code voor eenvoud)
# Let op: De inhoud van templates.py is hier ondergebracht
BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <title>{{ title }} - API Gateway V2</title>
    <meta charset="UTF-8">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root { --primary: #3b82f6; --bg: #0f172a; --card: #1e293b; --text: #f1f5f9; --text-muted: #94a3b8; --border: #334155; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }

        /* Sidebar */
        .sidebar { width: 260px; background: var(--card); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: 1.5rem; }
        .logo { font-size: 1.3rem; font-weight: 700; color: #fff; margin-bottom: 2rem; display: flex; align-items: center; gap: 10px; }
        .nav-item { display: flex; align-items: center; padding: 0.75rem 1rem; color: var(--text-muted); text-decoration: none; border-radius: 0.5rem; margin-bottom: 0.25rem; transition: 0.2s; }
        .nav-item:hover, .nav-item.active { background: #334155; color: #fff; }
        .nav-item i { width: 24px; }
        .section-title { font-size: 0.75rem; text-transform: uppercase; color: #64748b; margin: 1.5rem 0 0.5rem 0.5rem; font-weight: 600; }

        /* Main */
        .main { flex: 1; overflow-y: auto; padding: 2rem; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
        h1 { font-size: 1.8rem; font-weight: 600; }
        
        /* Utility */
        .alert { padding:1rem; margin-bottom:1rem; border-radius:0.5rem; }
        .alert-success { background: #166534; color: #86efac; }
        .alert-error { background: #7f1d1d; color: #fca5a5; }
        
        /* Stats, Cards, Forms */
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }
        .stat-card { background: var(--card); padding: 1.5rem; border-radius: 1rem; border: 1px solid var(--border); }
        .stat-label { color: var(--text-muted); font-size: 0.9rem; display: flex; justify-content: space-between; align-items: center; }
        .stat-value { font-size: 1.8rem; font-weight: 700; margin-top: 0.5rem; color: #fff; }
        .status-dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; }
        .status-online { background: #22c55e; box-shadow: 0 0 10px #22c55e; }
        .status-offline { background: #ef4444; }
        
        .btn { padding: 0.5rem 1rem; border-radius: 0.4rem; border: none; cursor: pointer; font-size: 0.9rem; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; color: white; }
        .btn-primary { background: var(--primary); }
        .btn-danger { background: #ef4444; }
        .btn-sm { padding: 0.3rem 0.6rem; font-size: 0.8rem; }
        .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
        .btn-ghost:hover { background: #334155; color: white; }
        
        /* Tables & Forms */
        .card-panel { background: var(--card); border-radius: 1rem; border: 1px solid var(--border); overflow: hidden; margin-bottom: 2rem; }
        .panel-header { padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: #182236; }
        .panel-title { font-size: 1.1rem; font-weight: 600; }
        .form-input, .form-select { width: 100%; padding: 0.6rem; background: #0f172a; border: 1px solid var(--border); color: white; border-radius: 0.4rem; }
        .form-group { margin-bottom: 1rem; }
        .form-label { display: block; margin-bottom: 0.5rem; color: var(--text-muted); font-size: 0.9rem; }
        
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 1rem 1.5rem; text-align: left; border-bottom: 1px solid var(--border); }
        th { color: var(--text-muted); font-weight: 500; font-size: 0.85rem; text-transform: uppercase; background: #182236; }
        tr:hover { background: #243046; }
        
        /* Modal Fix */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 100; align-items: center; justify-content: center; backdrop-filter: blur(2px); }
        .modal.active { display: flex; }
        .modal-content { background: var(--card); padding: 2rem; border-radius: 1rem; border: 1px solid var(--border); }

    </style>
</head>
<body>

    <nav class="sidebar">
        <div class="logo"><i class="fas fa-network-wired"></i> API Gateway V2</div>
        
        <div class="section-title">Menu</div>
        <a href="/dashboard" class="nav-item {{ 'active' if active_page == 'dashboard' else '' }}">
            <i class="fas fa-chart-line"></i> Dashboard
        </a>
        <a href="/endpoints" class="nav-item {{ 'active' if active_page == 'endpoints' else '' }}">
            <i class="fas fa-database"></i> Endpoints
        </a>
        
        <div class="section-title">Beheer</div>
        <a href="/users" class="nav-item {{ 'active' if active_page == 'users' else '' }}">
            <i class="fas fa-users"></i> Gebruikers
        </a>
        <a href="/migrate" class="nav-item {{ 'active' if active_page == 'migrate' else '' }}">
            <i class="fas fa-magic"></i> Migratie
        </a>
        
        <a href="/settings" class="nav-item {{ 'active' if active_page == 'settings' else '' }}" style="margin-top: auto;">
            <i class="fas fa-cogs"></i> Instellingen
        </a>
    </nav>

    <main class="main">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for c, m in messages %}
              <div class="alert alert-{{c}}">{{ m }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        {{ content | safe }}
    </main>

    <div id="addUserModal" class="modal">
        <div class="modal-content" style="max-width:400px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:1.5rem;">
                <h3>Nieuwe Gebruiker</h3>
                <span onclick="closeModal('addUserModal')" style="cursor:pointer; font-size:1.5rem; color:var(--text-muted)">&times;</span>
            </div>
            <form action="/users/add" method="POST">
                <div class="form-group">
                    <label class="form-label">Gebruikersnaam</label>
                    <input type="text" name="username" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Wachtwoord</label>
                    <input type="password" name="password" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Token Geldigheid</label>
                    <select name="validity" class="form-select">
                        <option value="24">24 Uur (Standaard)</option>
                        <option value="168">7 Dagen</option>
                        <option value="8760">1 Jaar</option>
                    </select>
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%">Aanmaken</button>
            </form>
        </div>
    </div>
    
    <div id="addEndpointModal" class="modal">
        <div class="modal-content" style="max-width:400px;">
            <h3>Nieuw Endpoint</h3><br>
            <form action="/manage/add" method="POST">
                <input type="text" name="app_name" class="form-input" placeholder="App Naam" style="margin-bottom:10px;" required>
                <input type="text" name="endpoint_name" class="form-input" placeholder="Endpoint Naam" style="margin-bottom:10px;" required>
                <button class="btn btn-primary" style="width:100%">Opslaan</button>
            </form>
            <br><button class="btn btn-ghost" style="width:100%" onclick="closeModal('addEndpointModal')">Annuleren</button>
        </div>
    </div>
    
    <div id="importModal" class="modal">
        <div class="modal-content" style="max-width:400px;">
            <h3>Importeer JSON</h3><br>
            <form id="importForm" action="" method="POST" enctype="multipart/form-data">
                <input type="file" name="file" class="form-input" style="margin-bottom:10px;" required>
                <button class="btn btn-primary" style="width:100%">Uploaden</button>
            </form>
            <br><button class="btn btn-ghost" style="width:100%" onclick="closeModal('importModal')">Annuleren</button>
        </div>
    </div>

    <script>
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
        function openImportModal(app, ep) {
            document.getElementById('importForm').action = `/manage/import/${app}/${ep}`;
            openModal('importModal');
        }
    </script>
</body>
</html>
"""

DASHBOARD_CONTENT = """
<div class="header">
    <h1>Systeem Status</h1>
    <span class="badge badge-blue">Host: {{ db_host }}</span>
</div>

<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-label">Database Status <div class="status-dot {{ 'status-online' if db_status else 'status-offline' }}"></div></div>
        <div class="stat-value">{{ 'Verbonden' if db_status else 'Fout' }}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Totale Opslag <i class="fas fa-hdd"></i></div>
        <div class="stat-value">{{ db_storage }}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Mislukte Logins (24u) <i class="fas fa-shield-alt"></i></div>
        <div class="stat-value" style="color: #ef4444;">{{ failed_logins }}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Totaal Endpoints <i class="fas fa-layer-group"></i></div>
        <div class="stat-value">{{ total_endpoints }}</div>
    </div>
</div>

<div class="card-panel">
    <div class="panel-header">
        <span class="panel-title">Activiteit (Afgelopen 7 dagen)</span>
    </div>
    <div style="padding: 1rem; height: 300px;">
        <canvas id="activityChart"></canvas>
    </div>
</div>

<script>
    const ctx = document.getElementById('activityChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: {{ chart_labels | safe }},
            datasets: [{
                label: 'Requests',
                data: {{ chart_data | safe }},
                backgroundColor: '#3b82f6',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: '#334155' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            },
            plugins: { legend: { display: false } }
        }
    });
</script>
"""

ENDPOINTS_CONTENT = """
<div class="header">
    <h1>Endpoints Data</h1>
    <button class="btn btn-primary" onclick="openModal('addEndpointModal')"><i class="fas fa-plus"></i> Nieuw</button>
</div>

<div class="stats-grid">
    {% for ep in endpoints %}
    <div class="stat-card">
        <div class="stat-label" style="margin-bottom: 0.5rem;">
            <span>{{ ep.app_name }}</span>
            <i class="fas fa-database" style="color: var(--primary);"></i>
        </div>
        <h3 style="color: white; margin-bottom: 0.25rem;">/{{ ep.endpoint_name }}</h3>
        <small style="color: var(--text-muted);">{{ ep.doc_count }} documenten</small>
        
        <div style="display: flex; gap: 5px; margin-top: 1rem;">
            <a href="/manage/export/{{ ep.app_name }}/{{ ep.endpoint_name }}" class="btn btn-sm btn-ghost" title="Backup"><i class="fas fa-download"></i></a>
            
            <button class="btn btn-sm btn-ghost" onclick="openImportModal('{{ ep.app_name }}', '{{ ep.endpoint_name }}')" title="Import"><i class="fas fa-upload"></i></button>
            
            <form action="/manage/empty" method="POST" onsubmit="return confirm('Weet je zeker dat je dit endpoint LEEG wilt maken? Alle data verdwijnt.');" style="display:inline;">
                <input type="hidden" name="app_name" value="{{ ep.app_name }}">
                <input type="hidden" name="endpoint_name" value="{{ ep.endpoint_name }}">
                <button class="btn btn-sm btn-ghost" style="color:orange;" title="Leegmaken (Truncate)"><i class="fas fa-eraser"></i></button>
            </form>

            <form action="/manage/delete" method="POST" onsubmit="return confirm('Verwijder endpoint definitief?');" style="display:inline;">
                <input type="hidden" name="app_name" value="{{ ep.app_name }}">
                <input type="hidden" name="endpoint_name" value="{{ ep.endpoint_name }}">
                <button class="btn btn-sm btn-ghost" style="color: #ef4444;" title="Verwijderen"><i class="fas fa-trash"></i></button>
            </form>
        </div>
    </div>
    {% endfor %}
</div>
"""

USERS_CONTENT = """
<div class="header">
    <h1>Gebruikersbeheer (Client API Toegang)</h1>
    <button class="btn btn-primary" onclick="openModal('addUserModal')"><i class="fas fa-plus"></i> Nieuwe Gebruiker</button>
</div>

<div class="card-panel">
    <table>
        <thead>
            <tr>
                <th>Gebruikersnaam</th>
                <th>Token Geldigheid</th>
                <th>Aangemaakt op</th>
                <th>Acties</th>
            </tr>
        </thead>
        <tbody>
            {% for user in users %}
            <tr>
                <td style="font-weight: 500; color: white;"><i class="fas fa-user-circle"></i> {{ user.username }}</td>
                <td>
                    <span class="badge badge-blue">
                        {{ user.token_validity_hours }} uur 
                        ({% if user.token_validity_hours == 24 %}1 dag{% elif user.token_validity_hours == 168 %}7 dagen{% elif user.token_validity_hours == 8760 %}1 jaar{% else %}Custom{% endif %})
                    </span>
                </td>
                <td>{{ user.created_at.strftime('%d-%m-%Y') if user.created_at else '-' }}</td>
                <td>
                    {% if user.username != 'admin' %}
                    <form action="/users/delete" method="POST" onsubmit="return confirm('Gebruiker verwijderen?');">
                        <input type="hidden" name="user_id" value="{{ user._id }}">
                        <button class="btn btn-sm btn-danger"><i class="fas fa-trash"></i></button>
                    </form>
                    {% else %}
                    <small class="text-muted">Dashboard User (niet verwijderbaar)</small>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

MIGRATION_CONTENT = """
<div class="header">
    <h1><i class="fas fa-magic"></i> Database Migratie</h1>
</div>
<p style="color: var(--text-muted); margin-bottom: 2rem;">
    Hieronder staan database collecties die nog niet gekoppeld zijn aan de nieuwe `/api/{app}/{endpoint}` structuur. 
    Geef ze een Applicatie- en Endpointnaam om ze te importeren.
</p>

{% if orphans %}
<div class="card-panel">
    <div class="panel-header"><span class="panel-title">Ongekoppelde Collecties</span></div>
    <div style="padding: 1rem;">
        {% for col in orphans %}
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding:10px 0;">
            <div>
                <span style="font-family: monospace; font-size: 1.1rem; color: #cbd5e1;">{{ col }}</span>
                <div style="font-size: 0.8rem; color: var(--text-muted);">{{ counts[col] }} documenten</div>
            </div>
            <form style="display:flex; gap:10px;" action="/migrate/do" method="POST">
                <input type="hidden" name="old_name" value="{{ col }}">
                <input type="text" name="new_app" placeholder="App Naam" class="form-input" style="width:120px;" required>
                <input type="text" name="new_ep" placeholder="Endpoint" class="form-input" style="width:120px;" required>
                <button type="submit" class="btn btn-sm btn-primary">Migreer</button>
            </form>
        </div>
        {% endfor %}
    </div>
</div>
{% else %}
<div style="text-align: center; color: var(--text-muted); padding: 4rem; background: var(--card); border-radius: 1rem; border: 1px solid var(--border);">
    <i class="fas fa-check-circle" style="font-size: 2rem; color: #22c55e;"></i><br><br>
    Geen ongekoppelde collecties gevonden. Alles is up-to-date!
</div>
{% endif %}
"""

SETTINGS_CONTENT = """
<div class="header">
    <h1><i class="fas fa-cogs"></i> Instellingen</h1>
</div>

<div class="stats-grid">
    <div class="stat-card" style="grid-column: span 2;">
        <div class="stat-label" style="margin-bottom: 1rem;"><span>Database Connectie</span></div>
        
        <form method="POST">
            <div class="form-group">
                <label class="form-label">Host / IP Adres</label>
                <input type="text" name="host" class="form-input" value="{{ config.get('mongo_host', 'localhost') }}" required>
            </div>
            <div class="form-group">
                <label class="form-label">Poort</label>
                <input type="number" name="port" class="form-input" value="{{ config.get('mongo_port', 27017) }}" required>
            </div>
            <div class="form-group">
                <label class="form-label">Database User (Optioneel)</label>
                <input type="text" name="mongo_user" class="form-input" value="{{ config.get('mongo_user', '') }}" placeholder="Laat leeg indien geen auth">
            </div>
             <div class="form-group">
                <label class="form-label">Database Wachtwoord (Optioneel)</label>
                <input type="password" name="mongo_pass" class="form-input" value="" placeholder="Niet getoond om veiligheidsredenen">
                <input type="hidden" name="current_mongo_pass_hash" value="{{ config.get('mongo_pass_hash', '') }}">
            </div>

            <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Opslaan & Testen</button>
            <small style="color: var(--text-muted); margin-left: 1rem;">Huidige status: <span style="color:{{ 'lime' if db_status else 'red' }}; font-weight:bold;">{{ 'Verbonden' if db_status else 'Niet Verbonden' }}</span></small>
        </form>
    </div>
</div>
"""

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-key-change-me')
CORS(app)

# ------------------------------------------------------------------------------
# 1. CONFIGURATIE & DB STATE
# ------------------------------------------------------------------------------
CONFIG_FILE = 'config.json'
MONGO_CLIENT = None
DB = None
DB_HOST_STR = "Niet ingesteld"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

def get_db_connection(config):
    host = config.get('mongo_host', 'localhost')
    port = config.get('mongo_port', 27017)
    user = config.get('mongo_user', '')
    password = config.get('mongo_pass', '')
    
    if user and password:
        safe_user = urllib.parse.quote_plus(user)
        safe_pass = urllib.parse.quote_plus(password)
        uri = f"mongodb://{safe_user}:{safe_pass}@{host}:{port}/?authSource=admin"
    else:
        uri = f"mongodb://{host}:{port}/"
    
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        client.server_info()
        return client, client['api_gateway_v2'], host, True
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None, None, host, False

def connect_to_db_on_load():
    """Initialiseert de globale DB-verbinding bij het laden van de app."""
    global MONGO_CLIENT, DB, DB_HOST_STR
    config = load_config()
    
    if 'mongo_host' in config:
        client, database, host, status = get_db_connection(config)
        
        if status:
            MONGO_CLIENT, DB, DB_HOST_STR = client, database, host
            create_initial_user(DB) 
            return True
    return False

connect_to_db_on_load()


# ------------------------------------------------------------------------------
# 2. HELPER FUNCTIES
# ------------------------------------------------------------------------------

def get_col_name(app_n, ep_n):
    safe_a = "".join(x for x in app_n if x.isalnum() or x in "_-")
    safe_e = "".join(x for x in ep_n if x.isalnum() or x in "_-")
    return f"data_{safe_a}_{safe_e}"

def hash_pass(p): return hashpw(p.encode('utf-8'), gensalt()).decode('utf-8')

def create_initial_user(database):
    """Maakt admin user aan in de APPLICATIE database voor Client Auth."""
    try:
        if database['users'].count_documents({}) == 0:
            database['users'].insert_one({
                "username": "admin",
                "password_hash": hash_pass("admin123"),
                "token_validity_hours": 24,
                "created_at": datetime.datetime.utcnow()
            })
    except Exception as e:
        print(f"Error creating initial user: {e}")

def log_activity(endpoint="system"):
    if DB: DB['access_logs'].insert_one({"endpoint": endpoint, "timestamp": datetime.datetime.utcnow()})


# ------------------------------------------------------------------------------
# 3. DASHBOARD ROUTES (GEEN AUTH)
# ------------------------------------------------------------------------------

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    log_activity("dashboard_view")
    
    db_status, db_storage, failed_count, total_eps, chart_labels, chart_data = False, "N/A", 0, 0, json.dumps([]), json.dumps([])
    
    if DB:
        try:
            stats = DB.command("dbstats")
            storage_mb = round(stats.get('storageSize', 0) / (1024 * 1024), 2)
            db_storage = f"{storage_mb} MB"
            db_status = True
            
            yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            failed_count = DB['failed_logins'].count_documents({"timestamp": {"$gt": yesterday}})
            total_eps = DB['system_endpoints'].count_documents({})

            pipeline = [
                {"$match": {"timestamp": {"$gt": datetime.datetime.utcnow() - datetime.timedelta(days=7)}}},
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}}, "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}}
            ]
            chart_raw = list(DB['access_logs'].aggregate(pipeline))
            chart_labels = []
            chart_data = []
            for i in range(6, -1, -1):
                d = (datetime.datetime.utcnow() - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
                chart_labels.append(d)
                val = next((item['count'] for item in chart_raw if item['_id'] == d), 0)
                chart_data.append(val)
            chart_labels = json.dumps(chart_labels)
            chart_data = json.dumps(chart_data)
        except Exception as e:
            db_status = False
            flash(f"Kan geen statistieken ophalen: {e}", "error")

    content = render_template_string(DASHBOARD_CONTENT, 
                                  db_host=DB_HOST_STR,
                                  db_status=db_status,
                                  db_storage=db_storage,
                                  failed_logins=failed_count,
                                  total_endpoints=total_eps,
                                  chart_labels=chart_labels,
                                  chart_data=chart_data)
    
    return render_template_string(BASE_LAYOUT, title="Dashboard", active_page='dashboard', content=content)

@app.route('/endpoints')
def view_endpoints():
    if not DB: flash("Database niet verbonden. Ga naar Instellingen.", "error")
    all_metas = list(DB['system_endpoints'].find().sort("app_name", 1)) if DB else []
    for ep in all_metas:
        col = get_col_name(ep['app_name'], ep['endpoint_name'])
        ep['doc_count'] = DB[col].count_documents({}) if DB else 0
    
    content = render_template_string(ENDPOINTS_CONTENT, endpoints=all_metas)
    return render_template_string(BASE_LAYOUT, title="Endpoints", active_page='endpoints', content=content)

@app.route('/users')
def view_users():
    if not DB: flash("Database niet verbonden. Ga naar Instellingen.", "error")
    users = list(DB['users'].find()) if DB else []
    content = render_template_string(USERS_CONTENT, users=users)
    return render_template_string(BASE_LAYOUT, title="Gebruikers", active_page='users', content=content)

@app.route('/migrate')
def migration_page():
    if not DB: 
        flash("Database niet verbonden. Ga naar Instellingen.", "error")
        orphans = []
        counts = {}
    else:
        all_cols = DB.list_collection_names()
        known_endpoints = list(DB['system_endpoints'].find())
        known_cols = [get_col_name(x['app_name'], x['endpoint_name']) for x in known_endpoints]
        known_cols.extend(['system_endpoints', 'users', 'access_logs', 'failed_logins'])
        orphans = [c for c in all_cols if c not in known_cols]
        counts = {c: DB[c].count_documents({}) for c in orphans}
    
    content = render_template_string(MIGRATION_CONTENT, orphans=orphans, counts=counts)
    return render_template_string(BASE_LAYOUT, title="Migratie", active_page='migrate', content=content)

@app.route('/settings', methods=['GET', 'POST'])
def settings_page():
    global MONGO_CLIENT, DB, DB_HOST_STR
    config = load_config()
    db_status = True if DB else False
    
    if request.method == 'POST':
        host = request.form.get('host')
        port = request.form.get('port')
        user = request.form.get('mongo_user', '')
        password = request.form.get('mongo_pass', '')
        
        # Behandel wachtwoord: gebruik bestaande hash als nieuw veld leeg is
        pass_hash = config.get('mongo_pass_hash', '')
        if password:
            pass_hash = hash_pass(password)
            
        # Nieuwe configuratie
        new_config = {
            'mongo_host': host,
            'mongo_port': int(port),
            'mongo_user': user,
            'mongo_pass': password, 
            'mongo_pass_hash': pass_hash 
        }

        # Test verbinding met de nieuwe configuratie
        client, database, db_host, status = get_db_connection(new_config)
        
        if status:
            save_config(new_config) 
            MONGO_CLIENT, DB, DB_HOST_STR = client, database, db_host
            db_status = True
            create_initial_user(DB) 
            flash("Database verbinding succesvol opgeslagen!", "success")
        else:
            flash("Fout bij verbinden met database. Controleer de gegevens.", "error")
            db_status = False

    config = load_config() 
    config['mongo_pass'] = '' # Toon wachtwoord niet in het veld
    
    content = render_template_string(SETTINGS_CONTENT, config=config, db_status=db_status)
    return render_template_string(BASE_LAYOUT, title="Instellingen", active_page='settings', content=content)


# ------------------------------------------------------------------------------
# 4. CRUD/MIGRATIE (Rely on global 'DB' being set)
# ------------------------------------------------------------------------------

@app.route('/migrate/do', methods=['POST'])
def do_migration():
    if not DB: return redirect(url_for('settings_page'))
    old_name = request.form.get('old_name')
    new_app = request.form.get('new_app')
    new_ep = request.form.get('new_ep')
    
    if DB['system_endpoints'].find_one({"app_name": new_app, "endpoint_name": new_ep}):
        flash("Doel bestaat al", "error")
        return redirect('/migrate')
        
    new_col = get_col_name(new_app, new_ep)
    DB[old_name].rename(new_col)
    DB['system_endpoints'].insert_one({
        "app_name": new_app, "endpoint_name": new_ep,
        "description": f"Migrated from {old_name}", "created_at": datetime.datetime.utcnow()
    })
    flash("Migratie gelukt", "success")
    return redirect('/migrate')

@app.route('/users/add', methods=['POST'])
def add_user():
    if not DB: return redirect(url_for('settings_page'))
    u = request.form.get('username')
    p = request.form.get('password')
    val = int(request.form.get('validity', 24))
    if DB['users'].find_one({'username': u}):
        flash("Gebruiker bestaat al", "error")
    else:
        DB['users'].insert_one({
            "username": u, "password_hash": hash_pass(p),
            "token_validity_hours": val, "created_at": datetime.datetime.utcnow()
        })
        flash(f"Gebruiker {u} aangemaakt", "success")
    return redirect('/users')

@app.route('/users/delete', methods=['POST'])
def delete_user():
    if not DB: return redirect(url_for('settings_page'))
    uid = request.form.get('user_id')
    DB['users'].delete_one({"_id": ObjectId(uid)})
    flash("Gebruiker verwijderd", "success")
    return redirect('/users')

@app.route('/manage/add', methods=['POST'])
def add_endpoint():
    if not DB: return redirect(url_for('settings_page'))
    app_n = request.form.get('app_name')
    ep_n = request.form.get('endpoint_name')
    if DB['system_endpoints'].find_one({"app_name": app_n, "endpoint_name": ep_n}):
        flash("Endpoint bestaat al", "error")
    else:
        DB['system_endpoints'].insert_one({
            "app_name": app_n, "endpoint_name": ep_n, "created_at": datetime.datetime.utcnow()
        })
        flash("Endpoint aangemaakt", "success")
    return redirect('/endpoints')

@app.route('/manage/delete', methods=['POST'])
def delete_endpoint():
    if not DB: return redirect(url_for('settings_page'))
    app_n = request.form.get('app_name')
    ep_n = request.form.get('endpoint_name')
    col = get_col_name(app_n, ep_n)
    DB[col].drop()
    DB['system_endpoints'].delete_one({"app_name": app_n, "endpoint_name": ep_n})
    flash("Verwijderd", "success")
    return redirect('/endpoints')

@app.route('/manage/empty', methods=['POST'])
def empty_endpoint():
    if not DB: return redirect(url_for('settings_page'))
    app_n = request.form.get('app_name')
    ep_n = request.form.get('endpoint_name')
    DB[get_col_name(app_n, ep_n)].delete_many({})
    flash("Geleegd", "success")
    return redirect('/endpoints')

@app.route('/manage/export/<app_name>/<endpoint_name>')
def export_data(app_name, endpoint_name):
    if not DB: return redirect(url_for('settings_page'))
    col = get_col_name(app_name, endpoint_name)
    data = list(DB[col].find())
    return send_file(io.BytesIO(json_util.dumps(data, indent=2).encode()), mimetype='application/json', as_attachment=True, download_name=f"{app_name}_{endpoint_name}.json")

@app.route('/manage/import/<app_name>/<endpoint_name>', methods=['POST'])
def import_data(app_name, endpoint_name):
    if not DB: return redirect(url_for('settings_page'))
    f = request.files['file']
    try:
        data = json_util.loads(f.read())
        if isinstance(data, list):
            clean = [{k:v for k,v in d.items() if k!='_id'} for d in data]
            if clean: DB[get_col_name(app_name, endpoint_name)].insert_many(clean)
            flash(f"{len(clean)} items geïmporteerd", "success")
    except Exception as e: flash(f"Fout: {e}", "error")
    return redirect('/endpoints')

# ------------------------------------------------------------------------------
# 5. PUBLIEKE API
# ------------------------------------------------------------------------------
@app.route('/api/<app_name>/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
def api_handler(app_name, endpoint_name):
    if not DB: return jsonify({"error": "DB Offline"}), 503
    log_activity(f"{app_name}/{endpoint_name}")
    
    meta = DB['system_endpoints'].find_one({"app_name": app_name, "endpoint_name": endpoint_name})
    if not meta: return jsonify({"error": "Not Found"}), 404
    
    col = DB[get_col_name(app_name, endpoint_name)]
    
    if request.method == 'GET':
        return jsonify([{'id':str(d.pop('_id')), **d} for d in col.find()])
    elif request.method == 'POST':
        d = request.json or {}
        if "created_at" not in d: d["created_at"] = datetime.datetime.utcnow()
        res = col.insert_one(d)
        return jsonify({"id": str(res.inserted_id)}), 201
    elif request.method == 'DELETE':
        col.delete_many({})
        return jsonify({"status": "cleared"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
