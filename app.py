import os
import datetime
import json
import secrets
import time
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
# 1. CONFIGURATIE & DB VERBINDING (Met Setup Bestand)
# ------------------------------------------------------------------------------
CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(host, port):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"mongo_host": host, "mongo_port": int(port)}, f)

def get_db_connection():
    conf = load_config()
    # Als geen config, gebruik default of return None om setup te triggeren
    host = conf.get('mongo_host', 'localhost')
    port = conf.get('mongo_port', 27017)
    uri = f"mongodb://{host}:{port}/"
    
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        client.server_info() # Trigger check
        return client, client['api_gateway_v2'], host
    except Exception:
        return None, None, None

# Globale DB variabele (wordt bij elke request gecheckt/ververst indien nodig)
mongo_client, db, db_host_str = get_db_connection()

# ------------------------------------------------------------------------------
# 2. SETUP ROUTE (Indien geen DB)
# ------------------------------------------------------------------------------
@app.before_request
def check_db_setup():
    # Sla statische bestanden over en de setup route zelf
    if request.endpoint in ['static', 'setup_db']:
        return
    
    global mongo_client, db, db_host_str
    
    # Probeer verbinding te herstellen als die er niet is
    if not db:
        mongo_client, db, db_host_str = get_db_connection()
    
    # Als nog steeds geen DB, forceer naar setup pagina
    if not db:
        return render_template_string(SETUP_CONTENT)

@app.route('/setup', methods=['POST'])
def setup_db():
    host = request.form.get('host')
    port = request.form.get('port')
    
    # Test verbinding
    try:
        uri = f"mongodb://{host}:{port}/"
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        client.server_info()
        
        # Als gelukt, opslaan
        save_config(host, port)
        
        # Herlaad globaal
        global mongo_client, db, db_host_str
        mongo_client, db, db_host_str = get_db_connection()
        
        flash("Verbinding geslaagd!", "success")
        # Maak direct admin aan indien nodig
        create_initial_user()
        return redirect(url_for('login'))
    except Exception as e:
        flash(f"Kon niet verbinden: {e}", "error")
        return redirect('/') # Trigger de before_request weer

# ------------------------------------------------------------------------------
# 3. HELPERS & SECURITY
# ------------------------------------------------------------------------------
JWT_SECRET = os.environ.get('JWT_SECRET', secrets.token_urlsafe(32))
JWT_COOKIE = 'auth_token'

def get_col_name(app_n, ep_n):
    safe_a = "".join(x for x in app_n if x.isalnum() or x in "_-")
    safe_e = "".join(x for x in ep_n if x.isalnum() or x in "_-")
    return f"data_{safe_a}_{safe_e}"

def hash_pass(p): return hashpw(p.encode('utf-8'), gensalt()).decode('utf-8')
def check_pass(p, h): return checkpw(p.encode('utf-8'), h.encode('utf-8'))

def create_initial_user():
    if db and db['users'].count_documents({}) == 0:
        db['users'].insert_one({
            "username": "admin",
            "password_hash": hash_pass("admin123"),
            "token_validity_hours": 24,
            "created_at": datetime.datetime.utcnow()
        })

def log_activity(endpoint="system"):
    """Simpele logger voor de grafiek"""
    if db:
        db['access_logs'].insert_one({
            "endpoint": endpoint,
            "timestamp": datetime.datetime.utcnow()
        })

def log_failed_login(username):
    if db:
        db['failed_logins'].insert_one({
            "username": username,
            "timestamp": datetime.datetime.utcnow(),
            "ip": request.remote_addr
        })

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(JWT_COOKIE)
        if not token: return redirect(url_for('login'))
        try:
            jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        except:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ------------------------------------------------------------------------------
# 4. DASHBOARD ROUTES (Views)
# ------------------------------------------------------------------------------
@app.route('/')
@token_required
def dashboard():
    if not db: return redirect(url_for('setup_db')) # Safety fallback

    # -- LOGICA VOOR DASHBOARD HOME --
    
    # 1. DB Stats
    try:
        stats = db.command("dbstats")
        storage_mb = round(stats['storageSize'] / (1024 * 1024), 2)
        storage_str = f"{storage_mb} MB"
        db_status = True
    except:
        storage_str = "Unknown"
        db_status = False

    # 2. Failed Logins (last 24h)
    yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    failed_count = db['failed_logins'].count_documents({"timestamp": {"$gt": yesterday}})

    # 3. Chart Data (Activity last 7 days)
    # Aggregatie pijplijn om logjes te tellen per dag
    pipeline = [
        {"$match": {"timestamp": {"$gt": datetime.datetime.utcnow() - datetime.timedelta(days=7)}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    chart_raw = list(db['access_logs'].aggregate(pipeline))
    
    # Vul gaten in data
    chart_labels = []
    chart_data = []
    for i in range(6, -1, -1):
        d = (datetime.datetime.utcnow() - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
        chart_labels.append(d)
        val = next((item['count'] for item in chart_raw if item['_id'] == d), 0)
        chart_data.append(val)

    # 4. Total Endpoints
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
def migration_view():
    # Eenvoudige versie, hergebruik oude logica of redirect naar aparte template
    # Voor nu, stuur terug naar de vorige template logica (hier ingekort)
    return redirect(url_for('dashboard')) # Placeholder, voeg migratie HTML terug toe indien nodig

# ------------------------------------------------------------------------------
# 5. ACTIES (POST routes)
# ------------------------------------------------------------------------------

# --- LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if not db: return setup_db() # Catch
        
        u = request.form.get('username')
        p = request.form.get('password')
        user = db['users'].find_one({'username': u})
        
        if user and check_pass(p, user['password_hash']):
            # Geldigheid ophalen, standaard 24u
            hours = user.get('token_validity_hours', 24)
            exp_time = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
            
            token = jwt.encode({
                'sub': str(user['_id']),
                'exp': exp_time
            }, JWT_SECRET, algorithm='HS256')
            
            resp = make_response(redirect('/'))
            resp.set_cookie(JWT_COOKIE, token, httponly=True)
            return resp
        else:
            log_failed_login(u)
            flash("Ongeldig wachtwoord of gebruiker", "error")
            
    return render_template_string(LOGIN_CONTENT)

@app.route('/logout')
def logout():
    resp = make_response(redirect('/login'))
    resp.set_cookie(JWT_COOKIE, '', expires=0)
    return resp

# --- USER MANAGEMENT ---
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
            "username": u,
            "password_hash": hash_pass(p),
            "token_validity_hours": val,
            "created_at": datetime.datetime.utcnow()
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

# --- ENDPOINT ACTIONS ---
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
    flash("Endpoint en data verwijderd", "success")
    return redirect('/endpoints')

@app.route('/manage/empty', methods=['POST'])
@token_required
def empty_endpoint():
    app_n = request.form.get('app_name')
    ep_n = request.form.get('endpoint_name')
    col = get_col_name(app_n, ep_n)
    
    # Alleen data weg, endpoint blijft
    db[col].delete_many({})
    flash(f"Data van /api/{app_n}/{ep_n} gewist (Truncated).", "success")
    return redirect('/endpoints')

# --- IMPORT/EXPORT (Kort) ---
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
# 6. PUBLIEKE API (Logt activiteit voor grafiek)
# ------------------------------------------------------------------------------
@app.route('/api/<app_name>/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
def api_handler(app_name, endpoint_name):
    if not db: return jsonify({"error": "DB Offline"}), 503
    
    log_activity(f"{app_name}/{endpoint_name}") # Log voor grafiek
    
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
