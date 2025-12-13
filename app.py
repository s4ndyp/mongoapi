# app.py
import os
import datetime
import json
import secrets
import string
import re
from functools import wraps
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, session, make_response
from flask_cors import CORS 
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from bson import ObjectId

# IMPORTS voor JWT en hashing
import jwt 
from bcrypt import hashpw, gensalt, checkpw
import hashlib 

# IMPORT Templates
from templates import (
    LOGIN_CONTENT, BASE_LAYOUT, DASHBOARD_CONTENT, 
    ENDPOINTS_CONTENT, CLIENT_DETAIL_CONTENT, SETTINGS_CONTENT
)

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
MONGO_CLIENT = None
app = Flask(__name__)

# CORS aangepast
CORS(app, supports_credentials=True) 

app.config['MONGO_URI'] = DEFAULT_MONGO_URI 
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-this')

# CONFIGURATIE VOOR JWT
app.config['JWT_SECRET'] = os.environ.get('JWT_SECRET', secrets.token_urlsafe(32))
app.config['JWT_EXPIRY_MINUTES'] = 60 * 24 
app.config['JWT_COOKIE_NAME'] = 'auth_token' 

# --- Helper: Wachtwoord Hashing ---
def hash_password(password):
    return hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

def check_password(password, hashed):
    return checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# --- Helper: JWT Functies ---
def encode_auth_token(user_id, expiry_minutes=None):
    try:
        minutes = expiry_minutes if expiry_minutes is not None else app.config['JWT_EXPIRY_MINUTES']
        payload = {
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes),
            'iat': datetime.datetime.utcnow(),
            'sub': str(user_id)
        }
        return jwt.encode(payload, app.config.get('JWT_SECRET'), algorithm='HS256')
    except Exception as e:
        print(f"JWT Encoding Error: {e}")
        return None

def decode_auth_token(auth_token):
    try:
        payload = jwt.decode(auth_token, app.config.get('JWT_SECRET'), algorithms=['HS256'])
        return (True, payload['sub'])
    except jwt.ExpiredSignatureError:
        return (False, 'Token is verlopen.')
    except jwt.InvalidTokenError:
        return (False, 'Ongeldig token.')

# --- Helper: Opslag Formatteren ---
def format_size(size_bytes):
    if size_bytes == 0: return "0 KB"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(0)
    p = 1024
    while size_bytes >= p and i < len(size_name) - 1:
        size_bytes /= p
        i += 1
    return f"{size_bytes:.2f} {size_name[i]}"

# --- Helper: Tag Kleur Generatie ---
def get_tag_color_class(tag):
    hash_object = hashlib.sha1(tag.encode())
    hex_dig = hash_object.hexdigest()
    color_index = int(hex_dig, 16) % 6
    return f"tag-color-{color_index}"


# --- Database Connectie & Indexen ---
def ensure_indexes(db):
    try:
        db['statistics'].create_index([("timestamp", 1), ("source", 1)], background=True)
        db['statistics'].create_index("timestamp", expireAfterSeconds=31536000, background=True) 
        db['api_keys'].create_index("key", unique=True, background=True)
        db['api_keys'].create_index("client_id", unique=True, background=True)
        db['endpoints'].create_index("name", unique=True, background=True)
        db['users'].create_index("username", unique=True, background=True)
        db['data_items'].create_index([("projectId", 1), ("type", 1)], background=True)
        db['data_projects'].create_index([("name", 1)], background=True)
        db['data_items'].create_index("meta.client_id", background=True)
        db['data_projects'].create_index("meta.client_id", background=True)
        print("MongoDB Indexen gecontroleerd.")
    except Exception as e:
        print(f"Waarschuwing indexen: {e}")

def get_db_connection(uri=None):
    global MONGO_CLIENT
    target_uri = uri if uri else app.config.get('MONGO_URI')

    if not target_uri: return None, "URI missing"

    if MONGO_CLIENT is None or uri is not None:
        try:
            client = MongoClient(target_uri, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            if uri is None:
                MONGO_CLIENT = client
                ensure_indexes(MONGO_CLIENT['api_gateway_db'])
            else:
                return client, None
            return MONGO_CLIENT, None
        except Exception as e:
            return None, str(e)
            
    try:
        MONGO_CLIENT.admin.command('ping')
        return MONGO_CLIENT, None
    except Exception as e:
        MONGO_CLIENT = None
        return None, str(e)

# --- Logging voor Statistieken ---
def log_statistic(action, source_app, endpoint="default"):
    client, _ = get_db_connection()
    if client:
        try:
            db = client['api_gateway_db']
            db['statistics'].insert_one({
                'timestamp': datetime.datetime.utcnow(),
                'action': action,
                'source': source_app,
                'endpoint': endpoint
            })
        except Exception as e:
            print(f"Log error: {e}")

# --- Endpoint Management Functies ---
def get_configured_endpoints(tag_filter=None):
    client, _ = get_db_connection()
    endpoints = []
    
    # Systeem Endpoints (Legacy)
    # Geef ze een standaard kleur (blauw/paars achtig)
    endpoints.append({
        'name': 'data',
        'description': 'Standaard Endpoint (Legacy / app_data)',
        'system': True,
        'tags': ['system', 'legacy'],
        'color': '#6c757d', # Grijs
        'created_at': datetime.datetime.min
    })
    
    endpoints.append({
        'name': 'items',
        'description': 'Taskey Items (Taken en Notities)',
        'system': True,
        'tags': ['system', 'taskey'],
        'color': '#0d6efd', # Blauw
        'created_at': datetime.datetime.min
    })
    endpoints.append({
        'name': 'projects',
        'description': 'Taskey Projecten',
        'system': True,
        'tags': ['system', 'taskey'],
        'color': '#0d6efd', # Blauw
        'created_at': datetime.datetime.min
    })

    if client:
        try:
            db_endpoints = list(client['api_gateway_db']['endpoints'].find({}, {'_id': 0}).sort('name', 1))
            for ep in db_endpoints:
                if ep.get('name') not in ['data', 'items', 'projects']: 
                    ep['system'] = False
                    ep['tags'] = ep.get('tags', [])
                    # Zorg voor een fallback kleur als deze nog niet bestaat in DB
                    if 'color' not in ep:
                         ep['color'] = '#198754' # Standaard groen
                    endpoints.append(ep)
        except Exception as e:
            print(f"Fout bij ophalen endpoints: {e}")
            
    if tag_filter:
        endpoints = [ep for ep in endpoints if tag_filter in ep.get('tags', [])]
        
    return endpoints

def get_all_unique_tags():
    client, _ = get_db_connection()
    tags = set(['system', 'taskey', 'legacy'])
    if client:
        try:
            db_tags = client['api_gateway_db']['endpoints'].distinct("tags")
            for t in db_tags: tags.add(t)
        except Exception as e: print(f"Error fetching tags: {e}")
    return sorted(list(tags))

def get_db_collection_name(endpoint_name):
    if endpoint_name == 'data': return 'app_data'
    elif endpoint_name == 'items': return 'data_items'
    elif endpoint_name == 'projects': return 'data_projects'
    else: return f"data_{endpoint_name}"

def get_endpoint_stats(endpoint_name):
    client, _ = get_db_connection()
    if not client: return {'count': 0, 'size': '0 KB'}
    coll_name = get_db_collection_name(endpoint_name)
    try:
        stats = client['api_gateway_db'].command("collstats", coll_name)
        return {'count': stats.get('count', 0), 'size': format_size(stats.get('storageSize', 0))}
    except:
        return {'count': 0, 'size': '0 KB'}

def process_tags_string(tags_str):
    if not tags_str: return []
    return [t.strip().lower() for t in tags_str.split(',') if t.strip()]

def create_endpoint(name, description, tags_str, color):
    if not re.match("^[a-zA-Z0-9_]+$", name):
        return False, "Naam mag alleen letters, cijfers en underscores bevatten."
    if name in ['data', 'items', 'projects']:
        return False, f"De naam '{name}' is gereserveerd voor het systeem."
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    
    tags = process_tags_string(tags_str)
    # Default kleur als leeg
    color = color if color else '#0d6efd'
    
    try:
        client['api_gateway_db']['endpoints'].insert_one({
            'name': name, 
            'description': description, 
            'tags': tags,
            'color': color,
            'created_at': datetime.datetime.utcnow()
        })
        client['api_gateway_db'].create_collection(get_db_collection_name(name))
        return True, None
    except Exception as e: return False, str(e)

def update_endpoint_metadata(name, description, tags_str, color):
    """Update de beschrijving, tags EN kleur."""
    if name in ['data', 'items', 'projects']:
        return False, "Systeem endpoints kunnen niet worden gewijzigd."
        
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    
    tags = process_tags_string(tags_str)
    color = color if color else '#0d6efd'
    
    try:
        result = client['api_gateway_db']['endpoints'].update_one(
            {'name': name},
            {'$set': {
                'description': description, 
                'tags': tags,
                'color': color
            }}
        )
        if result.matched_count == 0:
            return False, "Endpoint niet gevonden."
        return True, None
    except Exception as e: return False, str(e)

def delete_endpoint(name):
    if name in ['data', 'items', 'projects']: return False
    client, _ = get_db_connection()
    if not client: return False
    try:
        client['api_gateway_db']['endpoints'].delete_one({'name': name})
        client['api_gateway_db'][get_db_collection_name(name)].drop()
        return True
    except: return False

def clear_endpoint_data(name):
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    try:
        coll_name = get_db_collection_name(name)
        result = client['api_gateway_db'][coll_name].delete_many({})
        return True, result.deleted_count
    except Exception as e:
        return False, str(e)

# --- API Key Management ---
def load_api_keys():
    client, _ = get_db_connection()
    if not client: return {}
    keys = {}
    for doc in client['api_gateway_db']['api_keys'].find({}):
        keys[doc['client_id']] = {'key': doc['key'], 'description': doc['description']}
    return keys

def save_new_api_key(client_id, key, description): 
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    try:
        client['api_gateway_db']['api_keys'].insert_one({
            'client_id': client_id, 'key': key, 'description': description, 
            'created_at': datetime.datetime.utcnow()
        })
        return True, None
    except Exception as e: return False, str(e)

def revoke_api_key_db(client_id):
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    client['api_gateway_db']['api_keys'].delete_one({'client_id': client_id})
    return True, None

# --- USER MANAGEMENT FUNCTIES ---
def load_all_users():
    client, _ = get_db_connection()
    if not client: return []
    try:
        users = list(client['api_gateway_db']['users'].find({}, {'username': 1, 'created_at': 1, 'token_validity_minutes': 1}))
        return [{'username': u['username'], 'created_at': u['created_at'], 'validity': u.get('token_validity_minutes', 1440)} for u in users]
    except Exception as e:
        print(f"Error loading users: {e}")
        return []

def delete_user_db(username):
    client, _ = get_db_connection()
    if not client: return False, "No DB"
    try:
        client['api_gateway_db']['users'].delete_one({'username': username})
        return True, None
    except Exception as e:
        return False, str(e)

# --- AUTHENTICATIE ROUTE (JWT Login) ---
@app.route('/api/auth/login', methods=['POST'])
def login_api():
    client, _ = get_db_connection()
    data = request.json
    if not data or 'username' not in data or 'password' not in data:
        log_statistic("login_failed_invalid_input", get_remote_address(), "auth")
        return jsonify({"error": "Ongeldige input: gebruikersnaam en wachtwoord vereist."}), 400
        
    username = data['username']
    password = data['password']
    
    if not client: 
        log_statistic("login_failed_db_error", get_remote_address(), "auth")
        return jsonify({"error": "DB failure"}), 503
    
    db = client['api_gateway_db']
    user = db['users'].find_one({'username': username})
    
    if user and check_password(password, user['password_hash']):
        user_expiry = user.get('token_validity_minutes', app.config['JWT_EXPIRY_MINUTES'])
        token = encode_auth_token(user['_id'], user_expiry)
        log_statistic("login_success", username, "auth")
        
        response = make_response(jsonify({
            "status": "success", 
            "token": token,
            "expires_in_minutes": user_expiry,
            "message": "Token gegenereerd. Ook opgeslagen als HttpOnly cookie."
        }))
        response.set_cookie(app.config['JWT_COOKIE_NAME'], token, httponly=True, secure=False, samesite='Lax', max_age=user_expiry * 60)
        return response, 200
    else:
        log_statistic("login_failed", get_remote_address(), "auth")
        return jsonify({"error": "Ongeldige gebruikersnaam of wachtwoord."}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout_api():
    response = make_response(jsonify({"status": "success", "message": "Uitgelogd (Cookie gewist)."}))
    response.set_cookie(app.config['JWT_COOKIE_NAME'], '', expires=0, httponly=True)
    return response, 200
        
# --- Rate Limiter & Auth ---
def get_client_id():
    auth_header = request.headers.get('Authorization')
    token = None
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    if not token:
        token = request.cookies.get(app.config['JWT_COOKIE_NAME'])

    if token:
        client, _ = get_db_connection()
        if client:
            success, user_id_or_error = decode_auth_token(token)
            if success:
                db = client['api_gateway_db']
                user = db['users'].find_one({'_id': ObjectId(user_id_or_error)}, {'username': 1})
                return user['username'] if user else f"user_{user_id_or_error}"
            if auth_header:
                key_doc = client['api_gateway_db']['api_keys'].find_one({'key': token}, {'client_id': 1})
                if key_doc: return key_doc['client_id']
    return get_remote_address()

limiter = Limiter(key_func=get_client_id, app=app, default_limits=["2000 per day", "500 per hour"], storage_uri="memory://")

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS': return jsonify({'status': 'ok'}), 200
        token = None
        auth_type = "unknown"
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            auth_type = "header"
        if not token:
            token = request.cookies.get(app.config['JWT_COOKIE_NAME'])
            auth_type = "cookie"

        if not token: return jsonify({"error": "Authenticatie vereist (Bearer Token of Cookie)"}), 401
            
        client, _ = get_db_connection()
        success, user_id_or_error = decode_auth_token(token)
        
        if success:
            db = client['api_gateway_db']
            try:
                user = db['users'].find_one({'_id': ObjectId(user_id_or_error)}, {'username': 1})
                client_id = user['username'] if user else f"user_{user_id_or_error}"
                request.client_id = client_id
                return f(*args, **kwargs)
            except Exception as e:
                return jsonify({"error": f"Ongeldige JWT Sub. Detail: {e}"}), 401
        
        if auth_type == "header":
            jwt_error_detail = user_id_or_error
            client_id = None
            if client:
                db = client['api_gateway_db']
                key_doc = db['api_keys'].find_one({'key': token}, {'client_id': 1})
                if key_doc: client_id = key_doc['client_id']
            if client_id:
                request.client_id = client_id
                return f(*args, **kwargs)
            else:
                return jsonify({"error": f"Ongeldige Auth Token/Key. Detail: {jwt_error_detail}"}), 401
        else:
             return jsonify({"error": f"Sessie verlopen. (Detail: {user_id_or_error})"}), 401
    return wrapper

def require_dashboard_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash("Log eerst in om het dashboard te bekijken.", "warning")
            return redirect(url_for('dashboard_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_sidebar_data():
    if request.endpoint and 'static' not in request.endpoint:
        return dict(all_tags=get_all_unique_tags(), get_tag_color_class=get_tag_color_class)
    return dict()

# ---------------------------------------------------

# --- DASHBOARD LOGIC (Web Interface Routes) ---

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per 60 second", key_func=get_remote_address)
def dashboard_login():
    if 'username' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        client, _ = get_db_connection()
        username = request.form.get('username')
        password = request.form.get('password')
        if not client: 
            flash("DB fout: Kan geen verbinding maken.", "danger")
            return redirect(url_for('dashboard_login'))
        db = client['api_gateway_db']
        user = db['users'].find_one({'username': username})
        if user and check_password(password, user['password_hash']):
            session['username'] = username
            flash(f"Succesvol ingelogd als {username}.", "success")
            return redirect(url_for('dashboard'))
        else:
            log_statistic("login_failed_dashboard", get_remote_address(), "dashboard") 
            flash("Ongeldige gebruikersnaam of wachtwoord.", "danger")
            return redirect(url_for('dashboard_login'))
    content = render_template_string(LOGIN_CONTENT)
    return render_template_string(BASE_LAYOUT, page='login', page_content=content)

@app.errorhandler(429)
def ratelimit_handler(e):
    log_statistic("ratelimit_hit", get_remote_address(), "dashboard")
    flash(str(e.description), "danger")
    return redirect(url_for('dashboard_login'))

@app.route('/logout')
def dashboard_logout():
    session.pop('username', None)
    flash("Je bent uitgelogd.", "info")
    return redirect(url_for('dashboard_login'))

@app.route('/')
@require_dashboard_auth 
def dashboard():
    time_range = request.args.get('range', '6h')
    login_range = request.args.get('login_range', '24h') 
    
    range_map = {
        '6h': {'delta': datetime.timedelta(hours=6), 'label': 'Laatste 6 uur', 'group': '%H:00', 'fill': 'hour'},
        '24h': {'delta': datetime.timedelta(hours=24), 'label': 'Laatste 24 uur', 'group': '%H:00', 'fill': 'hour'},
        '7d': {'delta': datetime.timedelta(days=7), 'label': 'Laatste Week', 'group': '%a %d', 'fill': 'day'},
        '30d': {'delta': datetime.timedelta(days=30), 'label': 'Laatste Maand', 'group': '%d %b', 'fill': 'day'},
        '365d': {'delta': datetime.timedelta(days=365), 'label': 'Laatste Jaar', 'group': '%b %Y', 'fill': 'month'},
    }
    
    login_range_map = {
        '24h': {'delta': datetime.timedelta(hours=24), 'label': 'Laatste 24 Uur'},
        '7d': {'delta': datetime.timedelta(days=7), 'label': 'Laatste 7 Dagen'},
        '30d': {'delta': datetime.timedelta(days=30), 'label': 'Laatste 30 Dagen'},
    }
    
    current_range = range_map.get(time_range, range_map['6h'])
    current_login_range = login_range_map.get(login_range, login_range_map['24h'])
    
    start_time = datetime.datetime.utcnow() - current_range['delta']
    login_start_time = datetime.datetime.utcnow() - current_login_range['delta']
    
    client, _ = get_db_connection()
    db_connected = client is not None
    stats_count = 0
    unique_clients = []
    chart_data = {"labels": [], "counts": []}
    total_size = 0
    failed_logins = {} 

    if db_connected:
        try:
            db = client['api_gateway_db']
            yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            stats_count = db['statistics'].count_documents({'timestamp': {'$gte': yesterday}})
            unique_clients = db['statistics'].distinct('source', {'timestamp': {'$gte': yesterday}})
            
            endpoints = get_configured_endpoints()
            for ep in endpoints:
                 try: 
                    coll_name = get_db_collection_name(ep['name'])
                    s = db.command("collstats", coll_name)
                    total_size += s.get('storageSize', 0)
                 except: pass

            pipeline = [
                {'$match': {'timestamp': {'$gte': start_time}}},
                {'$group': {
                    '_id': {'$dateToString': {'format': current_range['group'], 'date': '$timestamp'}}, 
                    'count': {'$sum': 1},
                    'latest_time': {'$max': '$timestamp'}
                }},
                {'$sort': {'latest_time': 1}}
            ]
            agg_dict = {item['_id']: item['count'] for item in list(db['statistics'].aggregate(pipeline))}
            
            current = start_time
            now = datetime.datetime.utcnow()
            
            if current_range['fill'] == 'hour':
                step = datetime.timedelta(hours=1)
                current = current.replace(minute=0, second=0, microsecond=0)
                while current < now:
                    label = current.strftime(current_range['group'])
                    chart_data['labels'].append(label)
                    chart_data['counts'].append(agg_dict.get(label, 0))
                    current += step
            elif current_range['fill'] == 'day':
                step = datetime.timedelta(days=1)
                current = current.replace(hour=0, minute=0, second=0, microsecond=0)
                while current < now:
                    label = current.strftime(current_range['group'])
                    chart_data['labels'].append(label)
                    chart_data['counts'].append(agg_dict.get(label, 0))
                    current += step
            elif current_range['fill'] == 'month':
                current = datetime.datetime(current.year, current.month, 1)
                while current < now:
                    label = current.strftime(current_range['group'])
                    chart_data['labels'].append(label)
                    chart_data['counts'].append(agg_dict.get(label, 0))
                    nm = current.month + 1
                    ny = current.year
                    if nm > 12:
                        nm = 1
                        ny += 1
                    current = datetime.datetime(ny, nm, 1)

            failed_logins_pipeline = [
                {'$match': {
                    'action': {'$in': ['login_failed', 'login_failed_dashboard', 'login_failed_db_error', 'login_failed_invalid_input']},
                    'timestamp': {'$gte': login_start_time}
                }},
                {'$group': {
                    '_id': '$source',
                    'count': {'$sum': 1}
                }},
                {'$sort': {'count': -1}}
            ]
            failed_logins = {item['_id']: item['count'] for item in list(db['statistics'].aggregate(failed_logins_pipeline))}
        except Exception as e:
            print(f"Dashboard Data Error: {e}")
            pass
            
    content = render_template_string(DASHBOARD_CONTENT,
        db_connected=db_connected, stats_count=stats_count, client_count=len(unique_clients),
        clients=unique_clients, chart_data=chart_data, total_storage=format_size(total_size),
        time_range=time_range, current_range_label=current_range['label'],
        login_range=login_range, login_range_label=current_login_range['label'],
        failed_logins=failed_logins)
    return render_template_string(BASE_LAYOUT, page='dashboard', page_content=content)

@app.route('/endpoints', methods=['GET', 'POST'])
@require_dashboard_auth 
def endpoints_page():
    if request.method == 'POST':
        name = request.form.get('name')
        desc = request.form.get('description')
        tags = request.form.get('tags')
        color = request.form.get('color') # Nieuwe kleur parameter
        
        success, err = create_endpoint(name, desc, tags, color)
        if success: flash(f"Endpoint '{name}' aangemaakt.", "success")
        else: flash(f"Fout: {err}", "danger")
        return redirect(url_for('endpoints_page'))

    tag_filter = request.args.get('tag')
    endpoints = get_configured_endpoints(tag_filter=tag_filter)
    for ep in endpoints:
        ep['stats'] = get_endpoint_stats(ep['name'])
        
    content = render_template_string(ENDPOINTS_CONTENT, 
                                     endpoints=endpoints, 
                                     active_filter=tag_filter)
    return render_template_string(BASE_LAYOUT, page='endpoints', page_content=content)

@app.route('/endpoints/update', methods=['POST'])
@require_dashboard_auth
def update_endpoint_route():
    name = request.form.get('name')
    desc = request.form.get('description')
    tags = request.form.get('tags')
    color = request.form.get('color') # Nieuwe kleur parameter
    
    success, err = update_endpoint_metadata(name, desc, tags, color)
    if success: 
        flash(f"Endpoint '{name}' bijgewerkt.", "success")
    else: 
        flash(f"Fout bij updaten: {err}", "danger")
        
    return redirect(url_for('endpoints_page'))

@app.route('/endpoints/delete', methods=['POST'])
@require_dashboard_auth 
def delete_endpoint_route():
    name = request.form.get('name')
    if delete_endpoint(name): flash(f"Endpoint '{name}' verwijderd.", "warning")
    else: flash("Kon endpoint niet verwijderen.", "danger")
    return redirect(url_for('endpoints_page'))

@app.route('/endpoints/clear_data', methods=['POST'])
@require_dashboard_auth
def clear_data_route():
    name = request.form.get('name')
    success, result_or_err = clear_endpoint_data(name)
    if success:
        flash(f"Data van endpoint '{name}' succesvol gewist ({result_or_err} items verwijderd).", "success")
    else:
        flash(f"Kon data niet wissen: {result_or_err}", "danger")
    return redirect(url_for('endpoints_page'))

@app.route('/client/<source_app>')
@require_dashboard_auth 
def client_detail(source_app):
    client, _ = get_db_connection()
    logs = []
    total_requests = 0
    has_key = False
    is_user = False
    
    if client:
        db = client['api_gateway_db']
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        total_requests = db['statistics'].count_documents({'source': source_app, 'timestamp': {'$gte': yesterday}})
        if db['api_keys'].find_one({'client_id': source_app}): has_key = True
        if db['users'].find_one({'username': source_app}): is_user = True
        cursor = db['statistics'].find({'source': source_app}).sort('timestamp', -1).limit(20)
        for doc in cursor:
            logs.append({
                'timestamp': doc['timestamp'].isoformat(), 
                'action': doc.get('action', '-'),
                'endpoint': doc.get('endpoint', 'general')
            })
            
    content = render_template_string(CLIENT_DETAIL_CONTENT, 
                                   source_app=source_app, 
                                   logs=logs,
                                   total_requests=total_requests,
                                   has_key=has_key,
                                   is_user=is_user)
    return render_template_string(BASE_LAYOUT, page='detail', page_content=content)

@app.route('/settings', methods=['GET', 'POST'])
@require_dashboard_auth 
def settings():
    client, _ = get_db_connection()
    db = client['api_gateway_db'] if client else None
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_user':
            username = request.form.get('username')
            password = request.form.get('password')
            token_validity = int(request.form.get('token_validity_minutes', 1440))
            if db is None:
                flash("Fout: Geen DB verbinding.", "danger")
            elif not username or not password:
                flash("Fout: Gebruikersnaam en wachtwoord zijn verplicht.", "danger")
            else:
                try:
                    result = db['users'].insert_one({
                        'username': username,
                        'password_hash': hash_password(password),
                        'created_at': datetime.datetime.utcnow(),
                        'role': 'admin',
                        'token_validity_minutes': token_validity 
                    })
                    new_user_id = result.inserted_id
                    new_token = encode_auth_token(new_user_id, token_validity)
                    days = token_validity // 1440
                    time_msg = f"{days} dagen" if days >= 1 else "24 uur"
                    token_html = f"""
                    <p class="mb-2">Gebruiker **{username}** succesvol aangemaakt. Hier is het nieuwe JWT:</p>
                    <div class="d-flex align-items-center">
                        <input type="text" class="form-control bg-dark text-warning small font-monospace jwt-input-fix" readonly 
                            value="{new_token}" id="jwt-token-input">
                        <button type="button" class="btn btn-warning ms-2 flex-shrink-0" id="jwt-copy-button" title="Kopieer JWT">
                            <i class="bi bi-clipboard"></i> Kopieer Token
                        </button>
                    </div>
                    <p class="mt-2 small text-muted">Dit token is <b>{time_msg}</b> geldig.</p>
                    """
                    flash(token_html, "success")
                except OperationFailure as e:
                    if "E11000 duplicate key" in str(e): flash(f"Fout: Gebruikersnaam '{username}' bestaat al.", "danger")
                    else: flash(f"Fout bij aanmaken gebruiker: {e}", "danger")
                except Exception as e: flash(f"Onverwachte fout: {e}", "danger")

        elif action == 'delete_user':
            username = request.form.get('username')
            success, err = delete_user_db(username)
            if success: flash(f"Gebruiker '{username}' verwijderd. Actieve JWT's zijn ongeldig geworden.", "warning")
            else: flash(f"Fout: {err}", "danger")
        elif action == 'revoke_key':
            revoke_api_key_db(request.form.get('client_id'))
        elif action == 'save_uri':
            app.config['MONGO_URI'] = request.form.get('mongo_uri')
            flash("URI opgeslagen", "info")
            
        return redirect(url_for('settings'))

    api_keys = load_api_keys()
    active_users = load_all_users() 
    content = render_template_string(SETTINGS_CONTENT, 
                                     api_keys=api_keys, 
                                     active_users=active_users,
                                     current_uri=app.config['MONGO_URI'])
    return render_template_string(BASE_LAYOUT, page='settings', page_content=content)

@app.route('/api/health')
def health():
    client, _ = get_db_connection()
    return jsonify({"status": "running", "db": "ok" if client else "error"})

# --- DYNAMIC API ENDPOINT (General) ---
@app.route('/api/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
@require_auth
@limiter.limit("1000 per hour")
def handle_dynamic_endpoint(endpoint_name):
    client, _ = get_db_connection()
    if not client: return jsonify({"error": "DB failure"}), 503
    db = client['api_gateway_db']
    
    if endpoint_name not in ['data', 'items', 'projects'] and not db['endpoints'].find_one({'name': endpoint_name}):
        return jsonify({"error": f"Endpoint '{endpoint_name}' not found"}), 404

    coll_name = get_db_collection_name(endpoint_name)
    collection = db[coll_name]
    client_id = getattr(request, 'client_id', 'unknown')

    if request.method == 'POST':
        data = request.json
        if not data: return jsonify({"error": "No JSON"}), 400
        data['meta'] = {"created_at": datetime.datetime.utcnow(), "client_id": client_id}
        try:
            result = collection.insert_one(data)
            log_statistic("post_data", client_id, endpoint_name)
            saved_doc = collection.find_one({'_id': result.inserted_id})
            if saved_doc:
                saved_doc['id'] = str(saved_doc['_id'])
                del saved_doc['_id']
                return jsonify({"id": saved_doc['id'], "data": saved_doc}), 201
            else: return jsonify({"status": "created", "id": str(result.inserted_id), "data": {}}), 201
        except Exception as e:
            return jsonify({"error": f"Kon document niet opslaan: {e}"}), 500

    elif request.method == 'GET':
        query = {}
        for k, v in request.args.items():
            if k != '_limit': query[k] = v 
        query['meta.client_id'] = client_id
        limit = int(request.args.get('_limit', 50))
        docs = list(collection.find(query).sort("meta.created_at", -1).limit(limit))
        result_docs = []
        for d in docs:
            d['id'] = str(d['_id'])
            del d['_id']
            result_docs.append({"id": d['id'], "data": d })
        log_statistic("read_data", client_id, endpoint_name)
        return jsonify(result_docs), 200

    elif request.method == 'DELETE':
        query = {}
        for k, v in request.args.items(): query[k] = v
        if not query: return jsonify({"error": "DELETE requires query parameters for safety"}), 400
        query['meta.client_id'] = client_id
        result = collection.delete_many(query)
        log_statistic("delete_bulk", client_id, endpoint_name)
        return jsonify({"status": "deleted", "count": result.deleted_count}), 200

    return jsonify({"error": "Method not allowed"}), 405

# --- SINGLE DOCUMENT OPERATIONS ---
@app.route('/api/<endpoint_name>/<doc_id>', methods=['GET', 'PUT', 'DELETE'])
@require_auth
@limiter.limit("1000 per hour")
def handle_single_document(endpoint_name, doc_id):
    client, _ = get_db_connection()
    if not client: return jsonify({"error": "DB failure"}), 503
    db = client['api_gateway_db']

    coll_name = get_db_collection_name(endpoint_name)
    collection = db[coll_name]
    client_id = getattr(request, 'client_id', 'unknown')

    try: oid = ObjectId(doc_id)
    except: return jsonify({"error": "Invalid ID format"}), 400

    if request.method == 'GET':
        doc = collection.find_one({'_id': oid})
        if not doc: return jsonify({"error": "Not found"}), 404
        if doc.get('meta', {}).get('client_id') != client_id: return jsonify({"error": "Not found or access denied"}), 403
        doc['id'] = str(doc['_id'])
        del doc['_id']
        log_statistic("read_one", client_id, endpoint_name)
        return jsonify({"id": doc['id'], "data": doc}), 200

    elif request.method == 'PUT':
        data = request.json
        if not data: return jsonify({"error": "No JSON"}), 400
        update_doc = data.copy()
        if 'id' in update_doc: del update_doc['id'] 
        if '_id' in update_doc: del update_doc['_id'] 
        if 'meta' in update_doc: del update_doc['meta'] 
        update_doc['meta'] = data.get('meta', {})
        update_doc['meta']['updated_at'] = datetime.datetime.utcnow()
        update_doc['meta']['client_id'] = client_id 

        result = collection.update_one({'_id': oid, 'meta.client_id': client_id}, {'$set': update_doc})
        if result.matched_count == 0: return jsonify({"error": "Not found or access denied"}), 404
        updated_doc = collection.find_one({'_id': oid})
        updated_doc['id'] = str(updated_doc['_id'])
        del updated_doc['_id']
        log_statistic("update_one", client_id, endpoint_name)
        return jsonify({"id": updated_doc['id'], "data": updated_doc}), 200

    elif request.method == 'DELETE':
        result = collection.delete_one({'_id': oid, 'meta.client_id': client_id})
        if result.deleted_count == 0: return jsonify({"error": "Not found or access denied"}), 404
        log_statistic("delete_one", client_id, endpoint_name)
        return jsonify({"status": "deleted"}), 204

    return jsonify({"error": "Method not allowed"}), 405

if __name__ == '__main__':
    get_db_connection()
    app.run(host='0.0.0.0', port=5000, debug=True)
