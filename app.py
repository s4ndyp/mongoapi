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

# TEMPLATES (Let op: Layouts zijn nu direct in app.py)
from templates import BASE_LAYOUT, DASHBOARD_CONTENT, ENDPOINTS_CONTENT, USERS_CONTENT, MIGRATION_CONTENT, SETTINGS_CONTENT

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

JWT_SECRET = os.environ.get('JWT_SECRET', secrets.token_urlsafe(32))
JWT_COOKIE = 'auth_token'

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
            # Zorg dat de admin user bestaat (nodig voor Client Auth)
            create_initial_user(DB) 
            return True
    return False

# Probeer bij opstarten te verbinden (als config bestaat)
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
                "username": "dashboard_admin", # Nieuwe naam om verwarring te voorkomen
                "password_hash": hash_pass(secrets.token_urlsafe(16)), # Dummy wachtwoord, niet gebruikt
                "token_validity_hours": 24,
                "created_at": datetime.datetime.utcnow()
            })
            print("Default dashboard_admin user created for client auth checks.")
    except Exception as e:
        print(f"Error creating initial user: {e}")

def log_activity(endpoint="system"):
    if DB: DB['access_logs'].insert_one({"endpoint": endpoint, "timestamp": datetime.datetime.utcnow()})

def log_failed_login(username):
    if DB: DB['failed_logins'].insert_one({"username": username, "timestamp": datetime.datetime.utcnow(), "ip": request.remote_addr})

# De @token_required decorator is nu gedeactiveerd voor dashboard routes.
# De check is alleen nog relevant voor de API routes (indien nodig)

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
            'mongo_pass': password, # Let op: password veld in config is nu HASH
            'mongo_pass_hash': pass_hash 
        }

        # Test verbinding met de nieuwe configuratie
        client, database, db_host, status = get_db_connection(new_config)
        
        if status:
            # Succesvol, sla op en werk globale status bij
            save_config(new_config) 
            MONGO_CLIENT, DB, DB_HOST_STR = client, database, db_host
            db_status = True
            create_initial_user(DB) 
            flash("Database verbinding succesvol opgeslagen!", "success")
        else:
            flash("Fout bij verbinden met database. Controleer de gegevens.", "error")
            db_status = False

    # Haal de configuratie opnieuw op voor de GET-view
    config = load_config() 
    
    # We tonen geen wachtwoord in het veld, tonen de hash als hidden veld
    config['mongo_pass'] = '' 
    
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
