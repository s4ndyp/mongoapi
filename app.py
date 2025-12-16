import os
import json
import secrets
import datetime
import io
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, flash, session, send_file, make_response
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId, json_util

# ------------------------------------------------------------------------------
# IMPORT HTML TEMPLATES (Uit je templates.py)
# ------------------------------------------------------------------------------
from templates import LOGIN_CONTENT, DASHBOARD_CONTENT

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey_change_this')

# ------------------------------------------------------------------------------
# CONFIGURATIE & DB
# ------------------------------------------------------------------------------
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['api_gateway_v2']  # Database

# Metadata collectie
endpoints_meta = db['system_endpoints']

# JWT instellingen (voor de login beveiliging)
import jwt
APP_USER = "admin"
APP_PASS = "admin123"  # <--- WIJZIG DIT IN PRODUCTIE
JWT_SECRET = os.environ.get('JWT_SECRET', secrets.token_urlsafe(32))

# ------------------------------------------------------------------------------
# AUTHENTICATIE DECORATOR
# ------------------------------------------------------------------------------
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('auth_token')
        if not token:
            return redirect(url_for('login'))
        try:
            jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ------------------------------------------------------------------------------
# LOGIN ROUTES
# ------------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == APP_USER and password == APP_PASS:
            token = jwt.encode({
                'user': username,
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            }, JWT_SECRET, algorithm="HS256")
            
            resp = make_response(redirect(url_for('dashboard')))
            resp.set_cookie('auth_token', token, httponly=True)
            return resp
        else:
            flash("Ongeldige inloggegevens", "error")
            
    return render_template_string(LOGIN_CONTENT)

@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie('auth_token', '', expires=0)
    return resp

# ------------------------------------------------------------------------------
# DASHBOARD ROUTES (Beveiligd met @token_required)
# ------------------------------------------------------------------------------
@app.route('/')
@token_required
def dashboard():
    selected_app = request.args.get('app')
    
    # Haal alle metadata op
    all_metas = list(endpoints_meta.find().sort("app_name", 1))
    unique_apps = sorted(list(set([m['app_name'] for m in all_metas])))
    
    if selected_app:
        filtered_endpoints = [m for m in all_metas if m['app_name'] == selected_app]
    else:
        filtered_endpoints = all_metas

    # Voeg statistieken toe
    for ep in filtered_endpoints:
        col_name = get_data_collection_name(ep['app_name'], ep['endpoint_name'])
        ep['doc_count'] = db[col_name].count_documents({})

    return render_template_string(DASHBOARD_CONTENT, 
                                  apps=unique_apps, 
                                  endpoints=filtered_endpoints, 
                                  selected_app=selected_app)

# ------------------------------------------------------------------------------
# BEHEER (Create, Rename, Delete) - Beveiligd
# ------------------------------------------------------------------------------

def get_data_collection_name(app_name, endpoint_name):
    safe_app = "".join(x for x in app_name if x.isalnum() or x in "_-")
    safe_end = "".join(x for x in endpoint_name if x.isalnum() or x in "_-")
    return f"data_{safe_app}_{safe_end}"

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
# PUBLIEKE API ROUTES (Hier kan iedereen bij, of voeg auth toe indien gewenst)
# ------------------------------------------------------------------------------

def serialize(doc):
    doc['id'] = str(doc['_id'])
    del doc['_id']
    return doc

@app.route('/api/<app_name>/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
def api_handler(app_name, endpoint_name):
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
        # Let op: Publieke delete verwijdert alles? Misschien beveiligen!
        col.delete_many({})
        return jsonify({"status": "cleared"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
