import os
import datetime
import json
import secrets
import re
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, flash, make_response
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId, json_util

# Imports voor beveiliging
import jwt
from bcrypt import hashpw, gensalt, checkpw

# IMPORT HTML TEMPLATES
from templates import LOGIN_CONTENT, DASHBOARD_CONTENT

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-this')

# ------------------------------------------------------------------------------
# CONFIGURATIE & DB
# ------------------------------------------------------------------------------
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['api_gateway_v2']  # Zorg dat dit dezelfde DB naam is als je oude als je data wilt zien!
# Als je oude data in een andere DB zat, pas dan de naam hierboven aan (bijv 'api_gateway_db')

endpoints_meta = db['system_endpoints']
users_col = db['users']

app.config['JWT_SECRET'] = os.environ.get('JWT_SECRET', secrets.token_urlsafe(32))
app.config['JWT_EXPIRY_MINUTES'] = 60 * 24
app.config['JWT_COOKIE_NAME'] = 'auth_token'

# ------------------------------------------------------------------------------
# HULPFUNCTIES
# ------------------------------------------------------------------------------
def get_data_collection_name(app_name, endpoint_name):
    safe_app = "".join(x for x in app_name if x.isalnum() or x in "_-")
    safe_end = "".join(x for x in endpoint_name if x.isalnum() or x in "_-")
    return f"data_{safe_app}_{safe_end}"

def hash_password(password):
    return hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

def check_password_hash(password, hashed):
    return checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def encode_auth_token(user_id):
    try:
        payload = {
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=app.config['JWT_EXPIRY_MINUTES']),
            'iat': datetime.datetime.utcnow(),
            'sub': str(user_id)
        }
        return jwt.encode(payload, app.config.get('JWT_SECRET'), algorithm='HS256')
    except Exception as e:
        return None

def decode_auth_token(auth_token):
    try:
        payload = jwt.decode(auth_token, app.config.get('JWT_SECRET'), algorithms=['HS256'])
        return (True, payload['sub'])
    except:
        return (False, 'Ongeldig token')

def create_initial_user():
    if users_col.count_documents({}) == 0:
        print("--- ADMIN AANGEMAAKT (user: admin / pass: admin123) ---")
        users_col.insert_one({
            "username": "admin",
            "password_hash": hash_password("admin123"),
            "created_at": datetime.datetime.utcnow()
        })

create_initial_user()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(app.config['JWT_COOKIE_NAME'])
        if not token: return redirect(url_for('login'))
        success, _ = decode_auth_token(token)
        if not success: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ------------------------------------------------------------------------------
# MIGRATIE TOOL (NIEUW)
# ------------------------------------------------------------------------------
MIGRATION_HTML = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Migratie Tool</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body { background: #0f172a; color: #f1f5f9; font-family: 'Inter', sans-serif; padding: 2rem; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { margin-bottom: 2rem; border-bottom: 1px solid #334155; padding-bottom: 1rem; }
        .card { background: #1e293b; padding: 1.5rem; border-radius: 0.5rem; margin-bottom: 1rem; border: 1px solid #334155; display: flex; align-items: center; justify-content: space-between; }
        .old-name { font-family: monospace; font-size: 1.1rem; color: #cbd5e1; }
        .form-inline { display: flex; gap: 10px; align-items: center; }
        input { background: #0f172a; border: 1px solid #475569; color: white; padding: 0.5rem; border-radius: 0.25rem; }
        button { background: #2563eb; color: white; border: none; padding: 0.5rem 1rem; border-radius: 0.25rem; cursor: pointer; }
        button:hover { background: #1d4ed8; }
        .badge { background: #ef4444; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.8rem; margin-right: 10px; }
        .btn-back { display: inline-block; margin-bottom: 20px; color: #94a3b8; text-decoration: none; }
        .btn-back:hover { color: white; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="btn-back"><i class="fas fa-arrow-left"></i> Terug naar Dashboard</a>
        <h1><i class="fas fa-magic"></i> Database Migratie</h1>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div style="background: #166534; color: #86efac; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <p style="color: #94a3b8; margin-bottom: 2rem;">
            Hieronder staan database collecties die nog niet gekoppeld zijn aan de nieuwe structuur. 
            Geef ze een Applicatie- en Endpointnaam om ze te importeren.
        </p>

        {% for col in orphans %}
        <div class="card">
            <div>
                <span class="badge">Oud</span>
                <span class="old-name">{{ col }}</span>
                <div style="font-size: 0.8rem; color: #64748b; margin-top: 5px;">{{ counts[col] }} documenten</div>
            </div>
            <form class="form-inline" action="/migrate/do" method="POST">
                <input type="hidden" name="old_name" value="{{ col }}">
                <input type="text" name="new_app" placeholder="App Naam (bv. OudeApp)" required>
                <input type="text" name="new_ep" placeholder="Endpoint (bv. data)" required>
                <button type="submit">Migreer</button>
            </form>
        </div>
        {% else %}
            <div style="text-align: center; color: #64748b; padding: 3rem;">
                <i class="fas fa-check-circle" style="font-size: 2rem; color: #22c55e;"></i><br><br>
                Geen ongekoppelde collecties gevonden. Alles is up-to-date!
            </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/migrate')
@token_required
def migration_page():
    # Haal alle collecties op
    all_cols = db.list_collection_names()
    
    # Haal collecties op die we al kennen (uit metadata)
    known_endpoints = list(endpoints_meta.find())
    known_cols = [get_data_collection_name(x['app_name'], x['endpoint_name']) for x in known_endpoints]
    
    # Voeg systeem collecties toe aan 'bekend'
    known_cols.append('system_endpoints')
    known_cols.append('users')
    
    # Filter de wezen (orphans)
    orphans = [c for c in all_cols if c not in known_cols]
    
    # Tel documenten voor info
    counts = {c: db[c].count_documents({}) for c in orphans}
    
    return render_template_string(MIGRATION_HTML, orphans=orphans, counts=counts)

@app.route('/migrate/do', methods=['POST'])
@token_required
def do_migration():
    old_name = request.form.get('old_name')
    new_app = request.form.get('new_app')
    new_ep = request.form.get('new_ep')
    
    if not old_name or not new_app or not new_ep:
        flash("Vul alle velden in.", "error")
        return redirect(url_for('migration_page'))
        
    # Check of doel al bestaat
    if endpoints_meta.find_one({"app_name": new_app, "endpoint_name": new_ep}):
        flash(f"Het doel {new_app}/{new_ep} bestaat al. Kies een andere naam.", "error")
        return redirect(url_for('migration_page'))
        
    new_col_name = get_data_collection_name(new_app, new_ep)
    
    try:
        # 1. Hernoem de collectie in MongoDB
        db[old_name].rename(new_col_name)
        
        # 2. Maak metadata aan
        endpoints_meta.insert_one({
            "app_name": new_app,
            "endpoint_name": new_ep,
            "description": f"Gemigreerd van oude collectie: {old_name}",
            "created_at": datetime.datetime.utcnow()
        })
        
        flash(f"Succes! '{old_name}' is nu beschikbaar als '/api/{new_app}/{new_ep}'", "success")
    except Exception as e:
        flash(f"Fout bij migratie: {str(e)}", "error")
        
    return redirect(url_for('migration_page'))


# ------------------------------------------------------------------------------
# STANDAARD ROUTES (Dashboard, Login, API)
# ------------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = users_col.find_one({'username': username})
        
        if user and check_password_hash(password, user['password_hash']):
            token = encode_auth_token(user['_id'])
            resp = make_response(redirect(url_for('dashboard')))
            resp.set_cookie(app.config['JWT_COOKIE_NAME'], token, httponly=True)
            return resp
        else:
            flash("Ongeldige inloggegevens", "error")
    return render_template_string(LOGIN_CONTENT)

@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie(app.config['JWT_COOKIE_NAME'], '', expires=0)
    return resp

@app.route('/')
@token_required
def dashboard():
    selected_app = request.args.get('app')
    all_metas = list(endpoints_meta.find().sort("app_name", 1))
    unique_apps = sorted(list(set([m['app_name'] for m in all_metas])))
    filtered = [m for m in all_metas if m['app_name'] == selected_app] if selected_app else all_metas

    for ep in filtered:
        col = get_data_collection_name(ep['app_name'], ep['endpoint_name'])
        ep['doc_count'] = db[col].count_documents({})

    return render_template_string(DASHBOARD_CONTENT, apps=unique_apps, endpoints=filtered, selected_app=selected_app)

# --- Beheer Endpoints (Create, Rename, Delete) ---

@app.route('/manage/add', methods=['POST'])
@token_required
def add_endpoint():
    app_n = request.form.get('app_name')
    ep_n = request.form.get('endpoint_name')
    if endpoints_meta.find_one({"app_name": app_n, "endpoint_name": ep_n}):
        flash("Bestaat al", "error")
        return redirect(url_for('dashboard'))
    endpoints_meta.insert_one({
        "app_name": app_n, "endpoint_name": ep_n,
        "description": request.form.get('description', ''),
        "created_at": datetime.datetime.utcnow()
    })
    return redirect(url_for('dashboard', app=app_n))

@app.route('/manage/rename_app', methods=['POST'])
@token_required
def rename_application():
    old = request.form.get('old_app_name')
    new = request.form.get('new_app_name')
    for ep in endpoints_meta.find({"app_name": old}):
        old_c = get_data_collection_name(old, ep['endpoint_name'])
        new_c = get_data_collection_name(new, ep['endpoint_name'])
        if old_c in db.list_collection_names(): db[old_c].rename(new_c)
        endpoints_meta.update_one({"_id": ep["_id"]}, {"$set": {"app_name": new}})
    return redirect(url_for('dashboard', app=new))

@app.route('/manage/rename_endpoint', methods=['POST'])
@token_required
def rename_endpoint_route():
    app_n = request.form.get('app_name')
    old_e = request.form.get('old_endpoint_name')
    new_e = request.form.get('new_endpoint_name')
    old_c = get_data_collection_name(app_n, old_e)
    new_c = get_data_collection_name(app_n, new_e)
    if old_c in db.list_collection_names(): db[old_c].rename(new_c)
    endpoints_meta.update_one({"app_name": app_n, "endpoint_name": old_e}, {"$set": {"endpoint_name": new_e}})
    return redirect(url_for('dashboard', app=app_n))

@app.route('/manage/delete', methods=['POST'])
@token_required
def delete_endpoint():
    app_n = request.form.get('app_name')
    ep_n = request.form.get('endpoint_name')
    db[get_data_collection_name(app_n, ep_n)].drop()
    endpoints_meta.delete_one({"app_name": app_n, "endpoint_name": ep_n})
    return redirect(url_for('dashboard'))

# --- Import / Export ---

@app.route('/manage/export/<app_name>/<endpoint_name>')
@token_required
def export_data(app_name, endpoint_name):
    data = list(db[get_data_collection_name(app_name, endpoint_name)].find())
    return send_file(io.BytesIO(json_util.dumps(data, indent=2).encode('utf-8')), mimetype='application/json', as_attachment=True, download_name=f"{app_name}_{endpoint_name}.json")

@app.route('/manage/import/<app_name>/<endpoint_name>', methods=['POST'])
@token_required
def import_data(app_name, endpoint_name):
    if 'file' not in request.files: return redirect(url_for('dashboard'))
    try:
        data = json_util.loads(request.files['file'].read())
        if isinstance(data, list):
            cleaned = [{k:v for k,v in d.items() if k != '_id'} for d in data]
            if cleaned: db[get_data_collection_name(app_name, endpoint_name)].insert_many(cleaned)
    except: pass
    return redirect(url_for('dashboard', app=app_name))

# --- Publieke API ---

@app.route('/api/<app_name>/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
def api_handler(app_name, endpoint_name):
    if not endpoints_meta.find_one({"app_name": app_name, "endpoint_name": endpoint_name}):
        return jsonify({"error": "Endpoint not found"}), 404
    col = db[get_data_collection_name(app_name, endpoint_name)]
    
    if request.method == 'GET':
        return jsonify([{'id': str(d.pop('_id')), **d} for d in col.find()])
    elif request.method == 'POST':
        data = request.json or {}
        if "created_at" not in data: data["created_at"] = datetime.datetime.utcnow()
        res = col.insert_one(data)
        return jsonify({"id": str(res.inserted_id)}), 201
    elif request.method == 'DELETE':
        col.delete_many({})
        return jsonify({"status": "cleared"}), 200

# Import io en send_file (voor export)
import io
from flask import send_file

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
