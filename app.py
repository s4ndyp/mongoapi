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
# 1. CONFIGURATIE & DB VERBINDING (Met Setup Bestand)
# ------------------------------------------------------------------------------
CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_config(host, port, user, password):
    data = {
        "mongo_host": host, 
        "mongo_port": int(port),
        "mongo_user": user,
        "mongo_pass": password
    }
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f)

def get_db_connection():
    conf = load_config()
    host = conf.get('mongo_host', 'localhost')
    port = conf.get('mongo_port', 27017)
    user = conf.get('mongo_user', '')
    password = conf.get('mongo_pass', '')
    
    # Bouw URI: Alleen auth gebruiken als gebruiker dat in setup heeft ingevuld
    if user and password:
        # Veilige encoding
        safe_user = urllib.parse.quote_plus(user)
        safe_pass = urllib.parse.quote_plus(password)
        uri = f"mongodb://{safe_user}:{safe_pass}@{host}:{port}/?authSource=admin"
    else:
        # Onbeveiligde verbinding (standaard voor intern netwerk)
        uri = f"mongodb://{host}:{port}/"
    
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        client.server_info() # Trigger check
        return client, client['api_gateway_v2'], host
    except Exception as e:
        print(f"DB Error: {e}")
        return None, None, None

# Globale DB variabele
mongo_client, db, db_host_str = get_db_connection()

# ------------------------------------------------------------------------------
# 2. SETUP ROUTES (Infrastructure Setup)
# ------------------------------------------------------------------------------
@app.before_request
def check_db_setup():
    if request.endpoint in ['static', 'setup_db', 'reset_setup']:
        return
    
    global mongo_client, db, db_host_str
    
    # Als er geen DB object is, probeer te herladen (misschien net opgeslagen)
    if not db:
        mongo_client, db, db_host_str = get_db_connection()
    
    # Als NOG STEEDS geen DB, dan naar setup
    if not db:
        return render_template_string(SETUP_CONTENT)

@app.route('/setup', methods=['POST'])
def setup_db():
    host = request.form.get('host')
    port = request.form.get('port')
    # Optioneel: DB User/Pass (alleen als de server dat eist)
    user = request.form.get('mongo_user', '')
    password = request.form.get('mongo_pass', '')
    
    try:
        # 1. Test verbinding
        if user and password:
            safe_user = urllib.parse.quote_plus(user)
            safe_pass = urllib.parse.quote_plus(password)
            uri = f"mongodb://{safe_user}:{safe_pass}@{host}:{port}/?authSource=admin"
        else:
            uri = f"mongodb://{host}:{port}/"
            
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.server_info() # Check connection
        
        # 2. Als gelukt, opslaan
        save_config(host, port, user, password)
        
        # 3. Herlaad globaal
        global mongo_client, db, db_host_str
        mongo_client, db, db_host_str = get_db_connection()
        
        # 4. Zorg dat er een admin user bestaat in de database
        create_initial_user()
        
        flash("Server verbonden! Log nu in.", "success")
        return redirect(url_for('login'))
        
    except Exception as e:
        flash(f"Kon niet verbinden met server: {e}", "error")
        return redirect('/') 

@app.route('/setup/reset')
def reset_setup():
    # Helper om config te wissen als je vastzit
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    global db
    db = None
    return redirect('/')

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
    # Maakt admin user aan in de APPLICATIE database (niet de mongo server user)
    if db:
        try:
            if db['users'].count_documents({}) == 0:
                db['users'].insert_one({
                    "username": "admin",
                    "password_hash": hash_pass("admin123"),
                    "token_validity_hours": 24,
                    "created_at": datetime.datetime.utcnow()
                })
                print("Default admin user created.")
        except Exception as e:
            print(f"Error creating initial user: {e}")

def log_activity(endpoint="system"):
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
# 4. LOGIN & DASHBOARD ROUTES
# ------------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Dit is nu het APPLICATIE inlogscherm (Usercheck in de database)
    if request.method == 'POST':
        if not db: return redirect('/') # Terug naar setup als verbinding weg is
        
        u = request.form.get('username')
        p = request.form.get('password')
        
        # Zoek user in de collectie 'users'
        user = db['users'].find_one({'username': u})
        
        if user and check_pass(p, user['password_hash']):
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
            flash("Ongeldige inloggegevens.", "error")
            
    return render_template_string(LOGIN_CONTENT)

@app.route('/logout')
def logout():
    resp = make_response(redirect('/login'))
    resp.set_cookie(JWT_COOKIE, '', expires=0)
    return resp

@app.route('/')
@token_required
def dashboard():
    if not db: return redirect('/') 

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

# ------------------------------------------------------------------------------
# 5. ACTIES (CRUD)
# ------------------------------------------------------------------------------
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
