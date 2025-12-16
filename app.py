import os
import datetime
import json
import secrets
import string
import re
from functools import wraps
from flask import Flask, request, jsonify, redirect, url_for, flash, make_response, send_from_directory
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

# --- Globale Configuratie ---
DEFAULT_MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')
MONGO_CLIENT = None
app = Flask(__name__)

# CORS aangepast om credentials (cookies) toe te staan vanuit de frontend
CORS(app, supports_credentials=True, origins=["http://127.0.0.1:5000", "http://localhost:5000"]) 

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
            # Stuur een JSON 401 Unauthorized antwoord
            return jsonify({'error': 'Unauthorized', 'message': 'Sessie verlopen of ontbreekt.'}), 401

        payload = decode_jwt(token)
        if not payload:
            # Stuur een JSON 401 Unauthorized antwoord
            return jsonify({'error': 'Unauthorized', 'message': 'Ongeldige of verlopen token.'}), 401
        
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
        
        # 2. Rate Limiting (Globale Limiter wordt gebruikt)
        
        # Sla de client_id op in de g-object voor de endpoint functie
        g = globals()
        g['client_id'] = client_id
        return f(*args, **kwargs)
    return decorated_function

# --- Rate Limiter Setup (Globale rate limit) ---
# FIX: Pas de initialisatie aan naar het init_app patroon om de TypeError op te lossen.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000 per hour", "50 per minute"]
)
limiter.init_app(app)

@limiter.request_filter
def check_client_id_for_limit():
    client_id = request.headers.get('x-client-id') or request.args.get('client_id')
    if client_id:
        return False 
    return False

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
        
# --- Statische Bestanden Serveren (voor Dashboard) ---

@app.route('/')
def serve_dashboard():
    """
    Serveert het statische dashboard.html bestand vanaf de root URL.
    """
    # De directory is de map waarin app_universal.py draait.
    root_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(root_dir, 'dashboard.html')

# U kunt ook een aparte route toevoegen als u de URL /dashboard.html wilt behouden:
@app.route('/dashboard.html')
def serve_dashboard_file():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(root_dir, 'dashboard.html')


# --- API Route (Universeel Pad) ---
@app.route('/api/<path:endpoint_path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@check_api_key
def data_endpoint(endpoint_path):
    # Globale vars (client_id is ingesteld door check_api_key)
    g = globals()
    client_id = g['client_id']

    # 1. Pad ontleden
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
            pass 

    # 2. De unieke 'endpoint_name' (collectienaam) bepalen
    if doc_id:
        endpoint_parts = parts[:-1]
    else:
        endpoint_parts = parts

    endpoint_name = "_".join(endpoint_parts).lower()
    
    if not endpoint_name or len(endpoint_name) > 100: 
        return jsonify({"error": "Invalid or too long collection name derived from path."}), 400

    # 3. Database en Collectie
    db = get_db()
    if db is None: return jsonify({"error": "Database connection error"}), 503
    
    collection = db[endpoint_name] 

    # Logica voor GET (met of zonder ID)
    if request.method == 'GET':
        if doc_id:
            try:
                oid = ObjectId(doc_id)
            except:
                return jsonify({"error": "Invalid document ID format."}), 400
            
            doc = collection.find_one({'_id': oid, 'meta.client_id': client_id})
            if doc is None:
                return jsonify({"error": "Document not found or access denied."}), 404

            doc['id'] = str(doc['_id'])
            del doc['_id']
            log_statistic("get_one", client_id, endpoint_name)
            return jsonify({"id": doc['id'], "data": doc}), 200
        else:
            query_params = {k: v for k, v in request.args.items() if k not in ['api_key', 'client_id']}
            
            filter_query = {'meta.client_id': client_id}
            
            for key, value in query_params.items():
                if key.startswith('meta.'):
                    filter_query[key] = value
                else:
                    filter_query[f'data.{key}'] = value

            docs = list(collection.find(filter_query, {'_id': 1, 'id': 1, 'data': 1, 'meta': 1}))
            
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
        
        new_doc = {'data': data}
        
        new_doc['meta'] = {
            'created_at': datetime.datetime.utcnow(),
            'updated_at': datetime.datetime.utcnow(),
            'client_id': client_id,
        }

        if 'meta' in data:
            new_doc['meta'].update(data['meta'])
            del new_doc['data']['meta']

        try:
            result = collection.insert_one(new_doc)
            log_statistic("create_one", client_id, endpoint_name)
            
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
            
        update_set = {'data': data}
        
        update_set['meta'] = {'updated_at': datetime.datetime.utcnow(), 'client_id': client_id}
        
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

        result = collection.delete_one({'_id': oid, 'meta.client_id': client_id})
        
        if result.deleted_count == 0: 
            return jsonify({"error": "Not found or access denied"}), 404
            
        log_statistic("delete_one", client_id, endpoint_name)
        return jsonify({"message": f"Document {doc_id} from '{endpoint_name}' deleted."}), 200

    # Onbekende methode
    return jsonify({"error": "Method not allowed for this route."}), 405


# --- Dashboard API Routes ---

@app.route('/api/login', methods=['POST'])
def api_login():
    db = get_db()
    if db:
        create_initial_admin(db) 

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    user = db.users.find_one({'username': username})

    if user and check_password(password, user['password']):
        token = generate_jwt(user['username'])
        
        resp = make_response(jsonify({'message': 'Login succesvol'}), 200)
        resp.set_cookie(
            app.config['JWT_COOKIE_NAME'], 
            token, 
            httponly=True, 
            secure=app.config.get('ENV') == 'production',
            samesite='Lax',
            max_age=app.config['JWT_EXPIRY_MINUTES'] * 60
        )
        return resp
    else:
        return jsonify({'error': 'Ongeldige gebruikersnaam of wachtwoord'}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    resp = make_response(jsonify({'message': 'Succesvol uitgelogd'}), 200)
    resp.set_cookie(app.config['JWT_COOKIE_NAME'], '', expires=0, httponly=True, samesite='Lax')
    return resp

@app.route('/api/dashboard', methods=['GET'])
@check_auth
def api_dashboard():
    db = get_db()
    g = globals()
    user_id = g['user_id']
    
    pipeline = [
        {'$group': {'_id': '$endpoint', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 10}
    ]
    
    endpoint_stats = list(db.statistics.aggregate(pipeline))
    
    recent_activity = list(db.statistics.find().sort('timestamp', -1).limit(20))
    
    collection_names = db.list_collection_names()
    total_endpoints = len([name for name in collection_names if name not in ['users', 'clients', 'statistics', 'system.indexes']])
    total_clients = db.clients.count_documents({})
    total_calls = db.statistics.count_documents({})
    
    def format_doc(doc):
        doc['timestamp'] = doc['timestamp'].isoformat()
        return doc

    return jsonify({
        'user_id': user_id,
        'summary': {
            'endpoints_count': total_endpoints,
            'clients_count': total_clients,
            'calls_count': total_calls
        },
        'top_endpoints': endpoint_stats,
        'recent_activity': [format_doc(doc) for doc in recent_activity]
    })


@app.route('/api/settings', methods=['GET', 'POST', 'DELETE'])
@check_auth
def api_settings():
    db = get_db()
    g = globals()
    user_id = g['user_id']
    
    if request.method == 'GET':
        api_keys = []
        for client in db.clients.find({'user_id': user_id, 'revoked': False}):
            api_keys.append({
                'client_id': client['_id'], 
                'key': client['key'], 
                'description': client.get('description', 'N/A'),
                'created_at': client['created_at'].isoformat()
            })
        return jsonify({'api_keys': api_keys, 'user_id': user_id})

    elif request.method == 'POST':
        data = request.get_json()
        description = data.get('description', 'Nieuwe client')
        
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
        
        return jsonify({
            'message': 'Nieuwe API Sleutel gegenereerd', 
            'client_id': client_id, 
            'client_key': client_key
        }), 201

    elif request.method == 'DELETE':
        data = request.get_json()
        client_id_to_revoke = data.get('client_id')

        if not client_id_to_revoke:
            return jsonify({'error': 'Client ID ontbreekt.'}), 400

        result = db.clients.update_one(
            {'_id': client_id_to_revoke, 'user_id': user_id},
            {'$set': {'revoked': True}}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Client ID niet gevonden of geen toegang.'}), 404
        
        return jsonify({'message': f'API Sleutel ({client_id_to_revoke}) ingetrokken.'}), 200


if __name__ == '__main__':
    # Initialisatie van de DB en admin
    db = get_db()
    if db:
        create_initial_admin(db)
        
    # Start de Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)
