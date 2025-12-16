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

# Imports voor beveiliging (uit oude bestand)
import jwt
from bcrypt import hashpw, gensalt, checkpw

# IMPORT HTML TEMPLATES (Zorg dat templates.py in dezelfde map staat)
from templates import LOGIN_CONTENT, DASHBOARD_CONTENT

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-this')

# ------------------------------------------------------------------------------
# CONFIGURATIE & DB
# ------------------------------------------------------------------------------
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['api_gateway_v2']  # Nieuwe database naam

# Collecties
endpoints_meta = db['system_endpoints']
users_col = db['users']

# JWT Config (overgenomen uit oude bestand)
app.config['JWT_SECRET'] = os.environ.get('JWT_SECRET', secrets.token_urlsafe(32))
app.config['JWT_EXPIRY_MINUTES'] = 60 * 24  # 24 uur
app.config['JWT_COOKIE_NAME'] = 'auth_token'

# ------------------------------------------------------------------------------
# BEVEILIGING HELPERS (uit oude bestand)
# ------------------------------------------------------------------------------
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
        print(f"JWT Error: {e}")
        return None

def decode_auth_token(auth_token):
    try:
        payload = jwt.decode(auth_token, app.config.get('JWT_SECRET'), algorithms=['HS256'])
        return (True, payload['sub'])
    except jwt.ExpiredSignatureError:
        return (False, 'Token is verlopen.')
    except jwt.InvalidTokenError:
        return (False, 'Ongeldig token.')

def create_initial_user():
    """Maakt automatisch een admin user aan als er nog geen users zijn."""
    if users_col.count_documents({}) == 0:
        print("--- GEEN GEBRUIKERS GEVONDEN: MAAK STANDAARD ADMIN AAN ---")
        users_col.insert_one({
            "username": "admin",
            "password_hash": hash_password("admin123"),
            "created_at": datetime.datetime.utcnow()
        })
        print("--- ADMIN AANGEMAAKT (user: admin / pass: admin123) ---")

# Voer check uit bij opstarten
create_initial_user()

# ------------------------------------------------------------------------------
# AUTH DECORATOR
# ------------------------------------------------------------------------------
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(app.config['JWT_COOKIE_NAME'])
        
        if not token:
            return redirect(url_for('login'))
        
        success, result = decode_auth_token(token)
        if not success:
            flash(result, "error") # Toon reden (verlopen/ongeldig)
            return redirect(url_for('login'))
            
        return f(*args, **kwargs)
    return decorated

# ------------------------------------------------------------------------------
# LOGIN & LOGOUT ROUTES
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
            # HttpOnly cookie instellen (veiliger)
            resp.set_cookie(
                app.config['JWT_COOKIE_NAME'], 
                token, 
                httponly=True, 
                secure=False, # Zet op True als je HTTPS gebruikt
                samesite='Lax'
            )
            return resp
        else:
            flash("Ongeldige gebruikersnaam of wachtwoord", "error")
            
    return render_template_string(LOGIN_CONTENT)

@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie(app.config['JWT_COOKIE_NAME'], '', expires=0)
    flash("Succesvol uitgelogd", "success")
    return resp

# ------------------------------------------------------------------------------
# DASHBOARD ROUTES
# ------------------------------------------------------------------------------
def get_data_collection_name(app_name, endpoint_name):
    safe_app = "".join(x for x in app_name if x.isalnum() or x in "_-")
    safe_end = "".join(x for x in endpoint_name if x.isalnum() or x in "_-")
    return f"data_{safe_app}_{safe_end}"

@app.route('/')
@token_required
def dashboard():
    selected_app = request.args.get('app')
    
    all_metas = list(endpoints_meta.find().sort("app_name", 1))
    unique_apps = sorted(list(set([m['app_name'] for m in all_metas])))
    
    if selected_app:
        filtered_endpoints = [m for m in all_metas if m['app_name'] == selected_app]
    else:
        filtered_endpoints = all_metas

    for ep in filtered_endpoints:
        col_name = get_data_collection_name(ep['app_name'], ep['endpoint_name'])
        ep['doc_count'] = db[col_name].count_documents({})

    return render_template_string(DASHBOARD_CONTENT, 
                                  apps=unique_apps, 
                                  endpoints=filtered_endpoints, 
                                  selected_app=selected_app)

# ------------------------------------------------------------------------------
# BEHEER ROUTES
# ------------------------------------------------------------------------------
@app.route('/manage/add', methods=['POST'])
@token_required
def add_endpoint():
    app_name = request.form.get('app_name')
    endpoint_name = request.form.get('endpoint_name')
    description = request.form.get('description', '')

    if not app_name or not endpoint_name:
        flash("Vul alle velden in", "error")
        return redirect(url_for('dashboard'))

    exists = endpoints_meta.find_one({"app_name": app_name, "endpoint_name": endpoint_name})
    if exists:
        flash("Endpoint bestaat al", "error")
        return redirect(url_for('dashboard', app=app_name))

    endpoints_meta.insert_one({
        "app_name": app_name,
        "endpoint_name": endpoint_name,
        "description": description,
        "created_at": datetime.datetime.utcnow()
    })
    flash("Aangemaakt!", "success")
    return redirect(url_for('dashboard', app=app_name))

@app.route('/manage/rename_app', methods=['POST'])
@token_required
def rename_application():
    old = request.form.get('old_app_name')
    new = request.form.get('new_app_name')
    
    endpoints = list(endpoints_meta.find({"app_name": old}))
    for ep in endpoints:
        old_col = get_data_collection_name(old, ep['endpoint_name'])
        new_col = get_data_collection_name(new, ep['endpoint_name'])
        if old_col in db.list_collection_names():
            db[old_col].rename(new_col)
        endpoints_meta.update_one({"_id": ep["_id"]}, {"$set": {"app_name": new}})
        
    flash(f"Hernoemd naar {new}", "success")
    return redirect(url_for('dashboard', app=new))

@app.route('/manage/rename_endpoint', methods=['POST'])
@token_required
def rename_endpoint_route():
    app_name = request.form.get('app_name')
    old_ep = request.form.get('old_endpoint_name')
    new_ep = request.form.get('new_endpoint_name')
    
    old_col = get_data_collection_name(app_name, old_ep)
    new_col = get_data_collection_name(app_name, new_ep)
    
    if old_col in db.list_collection_names():
        db[old_col].rename(new_col)
        
    endpoints_meta.update_one(
        {"app_name": app_name, "endpoint_name": old_ep},
        {"$set": {"endpoint_name": new_ep}}
    )
    flash("Endpoint hernoemd", "success")
    return redirect(url_for('dashboard', app=app_name))

@app.route('/manage/delete', methods=['POST'])
@token_required
def delete_endpoint():
    app_name = request.form.get('app_name')
    ep_name = request.form.get('endpoint_name')
    col_name = get_data_collection_name(app_name, ep_name)
    db[col_name].drop()
    endpoints_meta.delete_one({"app_name": app_name, "endpoint_name": ep_name})
    flash("Verwijderd", "success")
    return redirect(url_for('dashboard'))

@app.route('/manage/export/<app_name>/<endpoint_name>')
@token_required
def export_data(app_name, endpoint_name):
    col = get_data_collection_name(app_name, endpoint_name)
    data = list(db[col].find())
    json_str = json_util.dumps(data, indent=2)
    return send_file(
        io.BytesIO(json_str.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f"{app_name}_{endpoint_name}.json"
    )

@app.route('/manage/import/<app_name>/<endpoint_name>', methods=['POST'])
@token_required
def import_data(app_name, endpoint_name):
    if 'file' not in request.files: return redirect(url_for('dashboard'))
    file = request.files['file']
    try:
        data = json_util.loads(file.read())
        if isinstance(data, list):
            col = get_data_collection_name(app_name, endpoint_name)
            cleaned = []
            for d in data:
                if "_id" in d: del d["_id"]
                cleaned.append(d)
            if cleaned: db[col].insert_many(cleaned)
            flash("Data geïmporteerd", "success")
    except Exception as e:
        flash(f"Fout: {e}", "error")
    return redirect(url_for('dashboard', app=app_name))

# ------------------------------------------------------------------------------
# PUBLIEKE API ROUTES
# ------------------------------------------------------------------------------
import io
from flask import send_file

def serialize(doc):
    doc['id'] = str(doc['_id'])
    del doc['_id']
    return doc

@app.route('/api/<app_name>/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
def api_handler(app_name, endpoint_name):
    # API endpoints zijn publiek. Wil je ze beveiligen? 
    # Voeg dan @token_required toe onder de @app.route regel.
    
    meta = endpoints_meta.find_one({"app_name": app_name, "endpoint_name": endpoint_name})
    if not meta: return jsonify({"error": "Endpoint not found"}), 404
    
    col = db[get_data_collection_name(app_name, endpoint_name)]

    if request.method == 'GET':
        return jsonify([serialize(d) for d in col.find()])
        
    if request.method == 'POST':
        data = request.json
        if not data: return jsonify({"error": "No JSON"}), 400
        if "created_at" not in data: data["created_at"] = datetime.datetime.utcnow()
        res = col.insert_one(data)
        return jsonify({"id": str(res.inserted_id)}), 201
        
    if request.method == 'DELETE':
        col.delete_many({})
        return jsonify({"status": "cleared"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
