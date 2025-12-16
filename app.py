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

# IMPORT Templates (Niet inbegrepen, maar functionele structuur behouden)
# from templates import (LOGIN_CONTENT, BASE_LAYOUT, DASHBOARD_CONTENT, ENDPOINTS_CONTENT, CLIENT_DETAIL_CONTENT, SETTINGS_CONTENT)
# Voor deze demonstratie gebruiken we placeholder templates

LOGIN_CONTENT = "Login UI"
BASE_LAYOUT = "<html><head><title>Universal API</title></head><body>{0}</body></html>"
DASHBOARD_CONTENT = "Dashboard UI"
ENDPOINTS_CONTENT = "Endpoints List"
CLIENT_DETAIL_CONTENT = "Client Detail"
SETTINGS_CONTENT = "Settings UI"

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
    # Wachtwoorden hashen
    return hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

def check_password(password, hashed_password):
    # Wachtwoord controleren
    return checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# --- Database Connectie ---
def get_db():
    global MONGO_CLIENT
    if MONGO_CLIENT is None:
        try:
            MONGO_CLIENT = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=5000)
            MONGO_CLIENT.admin.command('ping') 
            print("MongoDB connected!")
        except ConnectionFailure:
            print("ERROR: MongoDB connection failed!")
            return None
    return MONGO_CLIENT['data_store']

# --- JWT Helpers ---
def generate_jwt(user_id):
    # Genereer een JWT token
    payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=app.config['JWT_EXPIRY_MINUTES']),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')

def decode_jwt(token):
    # Decodeer een JWT token
    try:
        return jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# --- Decorators ---
def check_auth(f):
    # Decorator voor dashboard/admin authenticatie
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.cookies.get(app.config['JWT_COOKIE_NAME'])
        if not token:
            flash('Sessie verlopen, log opnieuw in.', 'warning')
            return redirect(url_for('dashboard_login'))

        payload = decode_jwt(token)
        if not payload:
            flash('Ongeldige of verlopen token, log opnieuw in.', 'warning')
            return redirect(url_for('dashboard_login'))
        
        # User ID in de g-object opslaan
        g = globals()
        g['user_id'] = payload['user_id']
        return f(*args, **kwargs)
    return decorated_function

def check_api_key(f):
    # Decorator voor API key authenticatie en rate limiting
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. API Sleutel en Client ID check
        client_key = request.headers.get('x-api-key') or request.args.get('api_key')
        client_id = request.headers.get('x-client-id') or request.args.get('client_id')

        if not client_key or not client_id:
            return jsonify({"error": "Missing x-api-key or x-client-id header/query parameter."}), 401

        db = get_db()
        if db is None: return jsonify({"error": "Database connection error"}), 503

        client = db.clients.find_one({'_id': client_id, 'key': client_key, 'revoked': False})
        
        if not client:
            return jsonify({"error": "Invalid client ID or API key."}), 401
        
        # 2. Rate Limiting (Moet hier geïntegreerd worden als Limiter niet op Flask-niveau wordt gebruikt)
        # Voor deze simpele Flask-versie vertrouwen we op de globale Limiter configuratie.
        
        # Sla de client_id op in de g-object voor de endpoint functie
        g = globals()
        g['client_id'] = client_id
        return f(*args, **kwargs)
    return decorated_function

# --- Rate Limiter Setup (Globale rate limit) ---
# De huidige Limiter-configuratie is globaal en werkt goed.
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["1000 per hour", "50 per minute"]
)
# We overschrijven de key_func voor API-calls met de client_id om per API key te limieten.
@limiter.request_filter
def check_client_id_for_limit():
    client_id = request.headers.get('x-client-id') or request.args.get('client_id')
    if client_id:
        # Dit zorgt ervoor dat de client_id wordt gebruikt als de rate limit key
        # We moeten wel een custom rate limit decorator maken om dit effectief te gebruiken
        # Voor nu houden we de standaard get_remote_address voor alle routes
        # Tenzij we de Limiter-logica naar binnen de check_api_key decorator verplaatsen.
        return False # Doorgaan met de standaard key_func (IP-adres)

# --- Endpoint Logica ---

def log_statistic(action, client_id, endpoint_name):
    # Log een API aanvraag
    db = get_db()
    try:
        db.statistics.insert_one({
            'timestamp': datetime.datetime.utcnow(),
            'client_id': client_id,
            'endpoint': endpoint_name,
            'action': action,
            'ip_address': get_remote_address()
        })
    except Exception as e:
        print(f"Log error: {e}")

def create_initial_admin(db):
    # Initialiseer de admin gebruiker als deze nog niet bestaat
    if db.users.count_documents({}) == 0:
        admin_pass = secrets.token_urlsafe(16)
        db.users.insert_one({
            'username': 'admin',
            'password': hash_password(admin_pass),
            'role': 'admin'
        })
        print(f"\n!!! EERSTE ADMIN GEBRUIKER AANGEMAAKT !!!")
        print(f"Gebruikersnaam: admin")
        print(f"Wachtwoord: {admin_pass}\n")
        
# --- API Route (Universeel Pad) ---

# De Flask route gebruikt <path:endpoint_path> om elk pad na /api/ op te vangen.
# Voorbeelden: /api/users, /api/users/doc_id, /api/group/resource, /api/group/resource/doc_id
@app.route('/api/<path:endpoint_path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@check_api_key
def data_endpoint(endpoint_path):
    # Globale vars (client_id is ingesteld door check_api_key)
    g = globals()
    client_id = g['client_id']

    # 1. Pad ontleden
    # Splitsen op '/' en lege componenten verwijderen
    parts = [p for p in endpoint_path.strip('/').split('/') if p]

    if not parts:
        return jsonify({"error": "Invalid API endpoint path. Path cannot be empty."}), 400

    doc_id = None
    
    # Controleer of de laatste component een MongoDB ObjectId is (24 hex karakters)
    if len(parts) > 1 and len(parts[-1]) == 24 and re.match("^[0-9a-fA-F]{24}$", parts[-1]):
        try:
            ObjectId(parts[-1])
            doc_id = parts[-1]
        except:
            pass # Geen geldige ObjectId, dus het is een deel van de collectienaam of een normale GET

    # 2. De unieke 'endpoint_name' (collectienaam) bepalen
    if doc_id:
        # Als we een doc_id hebben gevonden, is de collectienaam de rest van het pad
        endpoint_parts = parts[:-1]
    else:
        # Anders is het volledige pad de collectienaam
        endpoint_parts = parts

    # De collectienaam is de samenvoeging van de padcomponenten met een underscore.
    # Dit is de gesaneerde, universele collectie-ID: bijv. ['group', 'resource'] -> 'group_resource'
    endpoint_name = "_".join(endpoint_parts).lower()
    
    if not endpoint_name or len(endpoint_name) > 100: # Max lengte beperken
        return jsonify({"error": "Invalid or too long collection name derived from path."}), 400

    # 3. Database en Collectie
    db = get_db()
    if db is None: return jsonify({"error": "Database connection error"}), 503
    
    # Collectienaam dynamisch bepalen
    collection = db[endpoint_name] 

    # Logica voor GET (met of zonder ID)
    if request.method == 'GET':
        if doc_id:
            # GET /api/group/resource_id
            try:
                oid = ObjectId(doc_id)
            except:
                return jsonify({"error": "Invalid document ID format."}), 400
            
            # Zoeken op ID en client_id
            doc = collection.find_one({'_id': oid, 'meta.client_id': client_id})
            if doc is None:
                return jsonify({"error": "Document not found or access denied."}), 404

            doc['id'] = str(doc['_id'])
            del doc['_id']
            log_statistic("get_one", client_id, endpoint_name)
            return jsonify({"id": doc['id'], "data": doc}), 200
        else:
            # GET /api/group/resource
            # Optionele zoekparameters in de query string
            query_params = {k: v for k, v in request.args.items() if k not in ['api_key', 'client_id']}
            
            # Voeg client_id toe om alleen eigen documenten te tonen
            filter_query = {'meta.client_id': client_id}
            
            # Eenvoudige filtering op basis van query parameters
            # Let op: dit is een zeer simpele implementatie. Geen complexe MongoDB operators.
            for key, value in query_params.items():
                if key.startswith('meta.'):
                    filter_query[key] = value
                else:
                    # Zoek in het 'data' object (aangenomen dat alle data daar zit)
                    filter_query[f'data.{key}'] = value

            docs = list(collection.find(filter_query, {'_id': 1, 'id': 1, 'data': 1, 'meta': 1}))
            
            # Formatteer de resultaten
            results = []
            for doc in docs:
                doc['id'] = str(doc['_id'])
                del doc['_id']
                results.append({"id": doc['id'], "data": doc})

            log_statistic("get_many", client_id, endpoint_name)
            return jsonify(results), 200

    # Logica voor POST (nieuwe documenten)
    elif request.method == 'POST':
        if doc_id:
            return jsonify({"error": "POST request cannot include a document ID."}), 400

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload provided."}), 400
        
        # De payload moet de eigenlijke data zijn (volgens de platte structuur)
        new_doc = {'data': data}
        
        # Voeg metadata toe
        new_doc['meta'] = {
            'created_at': datetime.datetime.utcnow(),
            'updated_at': datetime.datetime.utcnow(),
            'client_id': client_id,
        }

        # Optionele 'meta' in de payload toevoegen als deze bestaat
        if 'meta' in data:
            new_doc['meta'].update(data['meta'])
            del new_doc['data']['meta'] # Zorg ervoor dat 'meta' niet dubbel in 'data' zit

        # Invoegen en ID ophalen
        try:
            result = collection.insert_one(new_doc)
            log_statistic("create_one", client_id, endpoint_name)
            
            # De return structuur volgt de verpakte aanpak
            return jsonify({
                "id": str(result.inserted_id), 
                "data": {
                    "data": new_doc['data'],
                    "meta": new_doc['meta'],
                    "id": str(result.inserted_id)
                }
            }), 201

        except OperationFailure as e:
            return jsonify({"error": f"Database error: {str(e)}"}), 500
            
    # Logica voor PUT/PATCH (volledige update)
    elif request.method == 'PUT':
        if not doc_id: return jsonify({"error": "PUT request requires a document ID."}), 400
        
        data = request.get_json()
        if not data: return jsonify({"error": "No JSON payload provided."}), 400

        try:
            oid = ObjectId(doc_id)
        except:
            return jsonify({"error": "Invalid document ID format."}), 400
            
        # De payload is de nieuwe 'data' inhoud
        update_set = {'data': data}
        
        # Update metadata
        update_set['meta'] = {'updated_at': datetime.datetime.utcnow(), 'client_id': client_id}
        
        # Gebruik de $set operator voor de update
        result = collection.update_one(
            {'_id': oid, 'meta.client_id': client_id}, 
            {'$set': update_set}
        )
        
        if result.matched_count == 0: 
            return jsonify({"error": "Not found or access denied"}), 404
            
        updated_doc = collection.find_one({'_id': oid})
        
        updated_doc['id'] = str(updated_doc['_id'])
        del updated_doc['_id']
        
        log_statistic("update_one", client_id, endpoint_name)
        # De return structuur volgt de verpakte aanpak
        return jsonify({
            "id": updated_doc['id'], 
            "data": {
                "data": updated_doc['data'],
                "meta": updated_doc['meta'],
                "id": updated_doc['id']
            }
        }), 200

    # Logica voor DELETE
    elif request.method == 'DELETE':
        if not doc_id: return jsonify({"error": "DELETE request requires a document ID."}), 400
        
        try:
            oid = ObjectId(doc_id)
        except:
            return jsonify({"error": "Invalid document ID format."}), 400

        # Verwijder op ID en client_id
        result = collection.delete_one({'_id': oid, 'meta.client_id': client_id})
        
        if result.deleted_count == 0: 
            return jsonify({"error": "Not found or access denied"}), 404
            
        log_statistic("delete_one", client_id, endpoint_name)
        return jsonify({"message": f"Document {doc_id} from '{endpoint_name}' deleted."}), 200

    # Onbekende methode
    return jsonify({"error": "Method not allowed for this route."}), 405


# --- Dashboard Routes (Behouden van de structuur) ---

# De rest van de dashboard/admin routes blijven ongewijzigd

@app.route('/', methods=['GET', 'POST'])
def dashboard_login():
    # Login logica...
    db = get_db()
    if db:
        create_initial_admin(db)

    if request.method == 'POST':
        # ... [Authenticatie logica] ...
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = db.users.find_one({'username': username})

        if user and check_password(password, user['password']):
            token = generate_jwt(user['username'])
            resp = make_response(redirect(url_for('dashboard')))
            resp.set_cookie(app.config['JWT_COOKIE_NAME'], token, httponly=True, secure=True, samesite='Lax')
            return resp
        else:
            flash('Ongeldige gebruikersnaam of wachtwoord.', 'danger')

    return render_template_string(BASE_LAYOUT.format(LOGIN_CONTENT))


@app.route('/dashboard')
@check_auth
def dashboard():
    # Dashboard logica...
    # ... [Ophalen van data voor dashboard] ...
    db = get_db()
    g = globals()
    user_id = g['user_id']
    
    # Haal de meest gebruikte endpoints op
    pipeline = [
        {'$group': {'_id': '$endpoint', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 10}
    ]
    
    endpoint_stats = list(db.statistics.aggregate(pipeline))
    
    # Haal de meest recente API aanvragen op
    recent_activity = list(db.statistics.find().sort('timestamp', -1).limit(20))
    
    # Haal de totale tellingen op
    total_endpoints = len(db.list_collection_names()) - 4 # Minus system collections
    total_clients = db.clients.count_documents({})
    total_calls = db.statistics.count_documents({})

    return render_template_string(BASE_LAYOUT.format(DASHBOARD_CONTENT), 
                                  endpoint_stats=endpoint_stats, 
                                  recent_activity=recent_activity,
                                  total_endpoints=total_endpoints,
                                  total_clients=total_clients,
                                  total_calls=total_calls,
                                  user_id=user_id)


@app.route('/logout')
def logout():
    # Logout logica...
    resp = make_response(redirect(url_for('dashboard_login')))
    resp.set_cookie(app.config['JWT_COOKIE_NAME'], '', expires=0, httponly=True, secure=True, samesite='Lax')
    flash('U bent uitgelogd.', 'success')
    return resp


@app.route('/settings', methods=['GET', 'POST'])
@check_auth
def settings():
    # Instellingen/Client beheer logica...
    db = get_db()
    g = globals()
    user_id = g['user_id']
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'generate_key':
            description = request.form.get('description')
            client_id = secrets.token_hex(8)
            client_key = secrets.token_urlsafe(32)
            
            db.clients.insert_one({
                '_id': client_id, 
                'key': client_key, 
                'user_id': user_id, 
                'description': description,
                'created_at': datetime.datetime.utcnow(),
                'revoked': False
            })
            flash(f'Nieuwe API Sleutel ({client_id}) gegenereerd.', 'success')
            
        elif action == 'revoke_key':
            client_id_to_revoke = request.form.get('client_id')
            db.clients.update_one(
                {'_id': client_id_to_revoke, 'user_id': user_id},
                {'$set': {'revoked': True}}
            )
            flash(f'API Sleutel ({client_id_to_revoke}) ingetrokken.', 'info')
            
        return redirect(url_for('settings'))

    api_keys = {}
    for client in db.clients.find({'user_id': user_id, 'revoked': False}):
        api_keys[client['_id']] = {'key': client['key'], 'description': client['description']}
        
    return render_template_string(BASE_LAYOUT.format(SETTINGS_CONTENT), api_keys=api_keys, user_id=user_id)

if __name__ == '__main__':
    # Initialisatie van de DB en admin
    db = get_db()
    if db:
        create_initial_admin(db)
        
    # Start de Flask app
    # Gebruik host='0.0.0.0' om extern bereikbaar te zijn
    app.run(host='0.0.0.0', port=5000, debug=True)
