# templates.py

# ------------------------------------------------------------------------------
# 1. SETUP PAGINA (Infrastructure Setup met Local Storage)
# ------------------------------------------------------------------------------
SETUP_CONTENT = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Setup - API Gateway</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body { background: #0f172a; color: #f1f5f9; font-family: 'Inter', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; width: 100%; max-width: 450px; border: 1px solid #334155; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); }
        h2 { margin-top: 0; color: #fff; text-align: center; }
        p { color: #94a3b8; text-align: center; margin-bottom: 2rem; font-size: 0.9rem; }
        label { display: block; margin-bottom: 0.5rem; font-size: 0.9rem; color: #cbd5e1; }
        input { width: 100%; padding: 0.75rem; background: #0f172a; border: 1px solid #334155; color: white; border-radius: 0.5rem; box-sizing: border-box; margin-bottom: 1rem; }
        input:focus { outline: none; border-color: #3b82f6; }
        button { width: 100%; padding: 0.75rem; background: #2563eb; color: white; border: none; border-radius: 0.5rem; font-weight: 600; cursor: pointer; margin-top: 1rem; }
        button:hover { background: #1d4ed8; }
        .alert { background: #7f1d1d; color: #fca5a5; padding: 0.75rem; border-radius: 0.5rem; margin-bottom: 1.5rem; font-size: 0.9rem; text-align: center; border: 1px solid #ef4444; }
        .section-header { font-size: 0.8rem; text-transform: uppercase; color: #64748b; margin-top: 1rem; margin-bottom: 0.5rem; font-weight: bold; border-bottom: 1px solid #334155; padding-bottom: 5px; }
        .hint { font-size: 0.8rem; color: #64748b; font-style: italic; margin-bottom: 10px; display: block; }
    </style>
</head>
<body>
    <div class="card">
        <h2><i class="fas fa-server"></i> Database Setup</h2>
        <p>Voer de MongoDB Server gegevens in.<br>Dit wordt lokaal in uw browser opgeslagen.</p>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form id="setupForm" onsubmit="handleSetup(event)">
            <div class="section-header">Database Server</div>
            <label>Host / IP Adres</label>
            <input type="text" id="host" value="localhost" placeholder="bv. localhost of 192.168.1.50" required>
            
            <label>Poort</label>
            <input type="number" id="port" value="27017" required>

            <div class="section-header">MongoDB Server Auth (Optioneel)</div>
            <span class="hint">Alleen invullen als de DB SERVER een wachtwoord vereist (laat anders leeg).</span>
            
            <label>Mongo Username</label>
            <input type="text" id="mongo_user" placeholder="Laat leeg indien geen auth">
            
            <label>Mongo Password</label>
            <input type="password" id="mongo_pass" placeholder="Laat leeg indien geen auth">
            
            <button type="submit">Opslaan & Doorgaan</button>
        </form>
    </div>
    
    <script>
        // Laad eventuele opgeslagen waarden
        document.getElementById('host').value = localStorage.getItem('db_host') || 'localhost';
        document.getElementById('port').value = localStorage.getItem('db_port') || '27017';
        document.getElementById('mongo_user').value = localStorage.getItem('db_user') || '';
        document.getElementById('mongo_pass').value = localStorage.getItem('db_pass') || '';


        function handleSetup(event) {
            event.preventDefault();

            // 1. Opslaan in Local Storage
            localStorage.setItem('db_host', document.getElementById('host').value);
            localStorage.setItem('db_port', document.getElementById('port').value);
            localStorage.setItem('db_user', document.getElementById('mongo_user').value);
            localStorage.setItem('db_pass', document.getElementById('mongo_pass').value);
            
            // 2. Redirect naar Login (de server zal de verbinding daar testen)
            window.location.href = '/login';
        }
    </script>
</body>
</html>
"""

# ------------------------------------------------------------------------------
# 2. LOGIN PAGINA (Applicatie Toegang, verstuurt DB config mee)
# ------------------------------------------------------------------------------
LOGIN_CONTENT = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Login - API Gateway</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body { background: #0f172a; color: #e2e8f0; font-family: 'Inter', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; width: 100%; max-width: 400px; border: 1px solid #334155; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); }
        h2 { text-align: center; margin-bottom: 0.5rem; color: #fff; }
        p { text-align: center; color: #94a3b8; margin-bottom: 2rem; font-size: 0.9rem; }
        input { width: 100%; padding: 0.75rem; background: #0f172a; border: 1px solid #334155; color: #fff; border-radius: 0.5rem; margin-bottom: 1.25rem; box-sizing: border-box; }
        input:focus { outline: none; border-color: #3b82f6; }
        button { width: 100%; padding: 0.75rem; background: #2563eb; color: white; border: none; border-radius: 0.5rem; font-weight: 600; cursor: pointer; }
        button:hover { background: #1d4ed8; }
        .alert { padding: 0.75rem; margin-bottom: 1.5rem; border-radius: 0.5rem; background: #450a0a; color: #fca5a5; border: 1px solid #b91c1c; text-align: center; font-size: 0.9rem; }
        .status-badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; background: #166534; color: #86efac; margin-bottom: 1rem; }
    </style>
</head>
<body>
    <div class="login-card">
        <div style="text-align: center;">
            <div class="status-badge"><i class="fas fa-check-circle"></i> Gereed voor Login</div>
        </div>
        <h2>Dashboard Login</h2>
        <p>Voer je applicatie inloggegevens in</p>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}{% for c, m in messages %}<div class="alert">{{ m }}</div>{% endfor %}{% endif %}
        {% endwith %}
        
        <form id="loginForm" method="POST" action="/login">
            <input type="hidden" name="db_host" id="db_host">
            <input type="hidden" name="db_port" id="db_port">
            <input type="hidden" name="db_user" id="db_user">
            <input type="hidden" name="db_pass" id="db_pass">

            <input type="text" name="username" placeholder="Gebruikersnaam (bv. admin)" required autofocus>
            <input type="password" name="password" placeholder="Wachtwoord" required>
            <button type="submit">Inloggen</button>
        </form>
        <div style="text-align: center; margin-top: 1rem;">
             <a href="#" onclick="clearDbConfig(event)" style="color: #64748b; font-size: 0.8rem; text-decoration: none;">Database verbinding wijzigen</a>
        </div>
    </div>

    <script>
        function loadDbConfig() {
            // Haal de DB-configuratie op uit Local Storage en vul de hidden fields
            document.getElementById('db_host').value = localStorage.getItem('db_host') || '';
            document.getElementById('db_port').value = localStorage.getItem('db_port') || '';
            document.getElementById('db_user').value = localStorage.getItem('db_user') || '';
            document.getElementById('db_pass').value = localStorage.getItem('db_pass') || '';

            // Controleer of de gegevens ontbreken. Zo ja, redirect naar setup.
            if (!document.getElementById('db_host').value || !document.getElementById('db_port').value) {
                window.location.href = '/';
                return false;
            }
            return true;
        }

        function clearDbConfig(event) {
            event.preventDefault();
            localStorage.removeItem('db_host');
            localStorage.removeItem('db_port');
            localStorage.removeItem('db_user');
            localStorage.removeItem('db_pass');
            window.location.href = '/';
        }

        // Zorg dat de gegevens geladen worden voordat het formulier wordt ingediend
        window.onload = loadDbConfig;
    </script>
</body>
</html>
"""

### 3. `app.py` (De herschreven serverlogica)
De `app.py` is nu volledig afhankelijk van de gegevens die de browser meestuurt tijdens de login. Dit voorkomt de `config.json` problemen.

```python
import os
import datetime
import json
import secrets
import time
import urllib.parse
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, flash, make_response
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from bson import ObjectId, json_util

# Security Libraries
import jwt 
from bcrypt import hashpw, gensalt, checkpw

# TEMPLATES
from templates import LOGIN_CONTENT, DASHBOARD_CONTENT, SETUP_CONTENT, MIGRATION_HTML

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-key-change-me')
CORS(app)

# ------------------------------------------------------------------------------
# 1. GLOBALE STATUS (Wordt pas gevuld na succesvolle login)
# ------------------------------------------------------------------------------
# We gebruiken deze nu om de status te behouden gedurende de sessie.
mongo_client = None
db = None
db_host_str = "Nog niet verbonden"

# Configuratie
JWT_SECRET = os.environ.get('JWT_SECRET', secrets.token_urlsafe(32))
JWT_COOKIE = 'auth_token'

# ------------------------------------------------------------------------------
# 2. DYNAMISCHE DB VERBINDING & HELPERS
# ------------------------------------------------------------------------------

def get_db_connection_dynamic(host, port, user="", password=""):
    """Probeert dynamisch een MongoDB-verbinding te maken."""
    try:
        if user and password:
            safe_user = urllib.parse.quote_plus(user)
            safe_pass = urllib.parse.quote_plus(password)
            uri = f"mongodb://{safe_user}:{safe_pass}@{host}:{port}/?authSource=admin"
        else:
            uri = f"mongodb://{host}:{port}/"
        
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.server_info()
        
        # Verbreek de verbinding als het de test doorstaat. Wordt opnieuw gemaakt bij succesvolle login.
        return client, client['api_gateway_v2'], host
    except Exception as e:
        print(f"DB Connection Test Failed: {e}")
        return None, None, None

def hash_pass(p): return hashpw(p.encode('utf-8'), gensalt()).decode('utf-8')
def check_pass(p, h): return checkpw(p.encode('utf-8'), h.encode('utf-8'))

def create_initial_user(database):
    """Maakt admin user aan in de APPLICATIE database."""
    try:
        if database['users'].count_documents({}) == 0:
            database['users'].insert_one({
                "username": "admin",
                "password_hash": hash_pass("admin123"),
                "token_validity_hours": 24,
                "created_at": datetime.datetime.utcnow()
            })
            print("Default admin user created.")
    except Exception as e:
        print(f"Error creating initial user: {e}")

def log_activity(endpoint="system"):
    if db: db['access_logs'].insert_one({"endpoint": endpoint, "timestamp": datetime.datetime.utcnow()})
def log_failed_login(username):
    if db: db['failed_logins'].insert_one({"username": username, "timestamp": datetime.datetime.utcnow(), "ip": request.remote_addr})

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not db: return redirect(url_for('setup_page'))
        token = request.cookies.get(JWT_COOKIE)
        if not token: return redirect(url_for('login'))
        try: jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        except: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ------------------------------------------------------------------------------
# 3. SETUP & INDEX ROUTING
# ------------------------------------------------------------------------------
@app.route('/')
def index():
    # Dit is de entry point. Als de globale verbinding nog niet is gezet,
    # sturen we de gebruiker naar de setup-pagina om de config op te halen.
    global db
    if db:
        return redirect(url_for('dashboard'))
    return redirect(url_for('setup_page'))

@app.route('/setup')
def setup_page():
    # Toon de setup pagina (deze pagina handelt opslag in Local Storage af)
    return render_template_string(SETUP_CONTENT)

# ------------------------------------------------------------------------------
# 4. LOGIN ROUTE (De cruciale aanpassing)
# ------------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    global mongo_client, db, db_host_str

    if request.method == 'POST':
        # 1. Haal ALLE inloggegevens op (DB én Applicatie)
        db_host = request.form.get('db_host')
        db_port = request.form.get('db_port')
        db_user = request.form.get('db_user', '')
        db_pass = request.form.get('db_pass', '')
        
        app_user = request.form.get('username')
        app_pass = request.form.get('password')

        # 2. Test/maak DB Connectie met de meegestuurde credentials
        temp_client, temp_db, temp_host = get_db_connection_dynamic(db_host, db_port, db_user, db_pass)
        
        if not temp_db:
            # Als DB Connectie mislukt, flash error en stuur terug naar login. 
            # De browser behoudt de DB-config in Local Storage.
            flash("Fout: Kan geen verbinding maken met de database. Controleer de serverinstellingen (IP/Poort).", "error")
            return redirect(url_for('login'))
        
        # 3. DB Connectie is gelukt! Zorg dat de Admin user bestaat (eerste keer)
        create_initial_user(temp_db)

        # 4. App Login check
        user = temp_db['users'].find_one({'username': app_user})
        
        if user and check_pass(app_pass, user['password_hash']):
            # Success! Sla de connectie globaal op in de server-sessie (globals)
            mongo_client, db, db_host_str = temp_client, temp_db, temp_host
            
            hours = user.get('token_validity_hours', 24)
            exp_time = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
            token = jwt.encode({'sub': str(user['_id']), 'exp': exp_time}, JWT_SECRET, algorithm='HS256')
            
            resp = make_response(redirect('/'))
            resp.set_cookie(JWT_COOKIE, token, httponly=True)
            return resp
        else:
            log_failed_login(app_user)
            flash("Ongeldige gebruikersnaam of wachtwoord.", "error")
            return redirect(url_for('login'))

    # GET Request: check if connection is active or config is ready
    return render_template_string(LOGIN_CONTENT)

@app.route('/logout')
def logout():
    # Wis ook de globale DB status
    global mongo_client, db, db_host_str
    mongo_client, db, db_host_str = None, None, "Nog niet verbonden"
    
    resp = make_response(redirect('/login'))
    resp.set_cookie(JWT_COOKIE, '', expires=0)
    return resp


# ------------------------------------------------------------------------------
# 5. DASHBOARD & CRUD ROUTES (Rely on global 'db' being set by successful login)
# ------------------------------------------------------------------------------
@app.route('/')
@token_required
def dashboard():
    # ... (Alle dashboard logica uit de vorige versie) ...
    # 1. DB Stats
    try:
        stats = db.command("dbstats")
        storage_mb = round(stats['storageSize'] / (1024 * 1024), 2)
        storage_str = f"{storage_mb} MB"
        db_status = True
    except:
        storage_str = "Unknown"
        db_status = False

    # 2. Failed Logins
    yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    failed_count = db['failed_logins'].count_documents({"timestamp": {"$gt": yesterday}})

    # 3. Chart Data
    pipeline = [
        {"$match": {"timestamp": {"$gt": datetime.datetime.utcnow() - datetime.timedelta(days=7)}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    chart_raw = list(db['access_logs'].aggregate(pipeline))
    
    chart_labels = []
    chart_data = []
    for i in range(6, -1, -1):
        d = (datetime.datetime.utcnow() - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
        chart_labels.append(d)
        val = next((item['count'] for item in chart_raw if item['_id'] == d), 0)
        chart_data.append(val)

    total_eps = db['system_endpoints'].count_documents({})

    return render_template_string(DASHBOARD_CONTENT, 
                                  active_page='dashboard',
                                  db_host=db_host_str,
                                  db_status=db_status,
                                  db_storage=storage_str,
                                  failed_logins=failed_count,
                                  total_endpoints=total_eps,
                                  chart_labels=json.dumps(chart_labels),
                                  chart_data=json.dumps(chart_data))

@app.route('/endpoints')
@token_required
def view_endpoints():
    all_metas = list(db['system_endpoints'].find().sort("app_name", 1))
    for ep in all_metas:
        col = get_col_name(ep['app_name'], ep['endpoint_name'])
        ep['doc_count'] = db[col].count_documents({})
    return render_template_string(DASHBOARD_CONTENT, active_page='endpoints', endpoints=all_metas)

@app.route('/users')
@token_required
def view_users():
    users = list(db['users'].find())
    return render_template_string(DASHBOARD_CONTENT, active_page='users', users=users)

@app.route('/migrate')
@token_required
def migration_page():
    all_cols = db.list_collection_names()
    known_endpoints = list(db['system_endpoints'].find())
    known_cols = [get_col_name(x['app_name'], x['endpoint_name']) for x in known_endpoints]
    known_cols.extend(['system_endpoints', 'users', 'access_logs', 'failed_logins'])
    
    orphans = [c for c in all_cols if c not in known_cols]
    counts = {c: db[c].count_documents({}) for c in orphans}
    
    return render_template_string(MIGRATION_HTML, orphans=orphans, counts=counts)

@app.route('/migrate/do', methods=['POST'])
@token_required
def do_migration():
    old_name = request.form.get('old_name')
    new_app = request.form.get('new_app')
    new_ep = request.form.get('new_ep')
    
    if db['system_endpoints'].find_one({"app_name": new_app, "endpoint_name": new_ep}):
        flash("Doel bestaat al", "error")
        return redirect('/migrate')
        
    new_col = get_col_name(new_app, new_ep)
    db[old_name].rename(new_col)
    db['system_endpoints'].insert_one({
        "app_name": new_app, "endpoint_name": new_ep,
        "description": f"Migrated from {old_name}", "created_at": datetime.datetime.utcnow()
    })
    flash("Migratie gelukt", "success")
    return redirect('/migrate')


@app.route('/users/add', methods=['POST'])
@token_required
def add_user():
    u = request.form.get('username')
    p = request.form.get('password')
    val = int(request.form.get('validity', 24))
    if db['users'].find_one({'username': u}):
        flash("Gebruiker bestaat al", "error")
    else:
        db['users'].insert_one({
            "username": u, "password_hash": hash_pass(p),
            "token_validity_hours": val, "created_at": datetime.datetime.utcnow()
        })
        flash(f"Gebruiker {u} aangemaakt", "success")
    return redirect('/users')

@app.route('/users/delete', methods=['POST'])
@token_required
def delete_user():
    uid = request.form.get('user_id')
    db['users'].delete_one({"_id": ObjectId(uid)})
    flash("Gebruiker verwijderd", "success")
    return redirect('/users')

@app.route('/manage/add', methods=['POST'])
@token_required
def add_endpoint():
    app_n = request.form.get('app_name')
    ep_n = request.form.get('endpoint_name')
    if db['system_endpoints'].find_one({"app_name": app_n, "endpoint_name": ep_n}):
        flash("Endpoint bestaat al", "error")
    else:
        db['system_endpoints'].insert_one({
            "app_name": app_n, "endpoint_name": ep_n, "created_at": datetime.datetime.utcnow()
        })
        flash("Endpoint aangemaakt", "success")
    return redirect('/endpoints')

@app.route('/manage/delete', methods=['POST'])
@token_required
def delete_endpoint():
    app_n = request.form.get('app_name')
    ep_n = request.form.get('endpoint_name')
    col = get_col_name(app_n, ep_n)
    db[col].drop()
    db['system_endpoints'].delete_one({"app_name": app_n, "endpoint_name": ep_n})
    flash("Verwijderd", "success")
    return redirect('/endpoints')

@app.route('/manage/empty', methods=['POST'])
@token_required
def empty_endpoint():
    app_n = request.form.get('app_name')
    ep_n = request.form.get('endpoint_name')
    db[get_col_name(app_n, ep_n)].delete_many({})
    flash("Geleegd", "success")
    return redirect('/endpoints')

@app.route('/manage/export/<app_name>/<endpoint_name>')
@token_required
def export_data(app_name, endpoint_name):
    import io
    from flask import send_file
    col = get_col_name(app_name, endpoint_name)
    data = list(db[col].find())
    return send_file(io.BytesIO(json_util.dumps(data, indent=2).encode()), mimetype='application/json', as_attachment=True, download_name=f"{app_name}_{endpoint_name}.json")

@app.route('/manage/import/<app_name>/<endpoint_name>', methods=['POST'])
@token_required
def import_data(app_name, endpoint_name):
    f = request.files['file']
    try:
        data = json_util.loads(f.read())
        if isinstance(data, list):
            clean = [{k:v for k,v in d.items() if k!='_id'} for d in data]
            if clean: db[get_col_name(app_name, endpoint_name)].insert_many(clean)
            flash(f"{len(clean)} items geïmporteerd", "success")
    except Exception as e: flash(f"Fout: {e}", "error")
    return redirect('/endpoints')

# ------------------------------------------------------------------------------
# 6. PUBLIEKE API
# ------------------------------------------------------------------------------
@app.route('/api/<app_name>/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
def api_handler(app_name, endpoint_name):
    # API endpoints vereisen een actieve DB verbinding, maar geen dashboard login.
    if not db: return jsonify({"error": "DB Offline"}), 503
    log_activity(f"{app_name}/{endpoint_name}")
    
    meta = db['system_endpoints'].find_one({"app_name": app_name, "endpoint_name": endpoint_name})
    if not meta: return jsonify({"error": "Not Found"}), 404
    
    col = db[get_col_name(app_name, endpoint_name)]
    
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
