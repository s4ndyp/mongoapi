import os
import datetime
import json
import secrets
import string
import re
import sys
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

# FIX: CORS Aangepast
# Om 'Failed to fetch' van externe clients op te lossen, staat de API nu alle origins toe (*).
CORS(app, origins="*") 

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

# --- JSON Serialisatie FIX ---
def format_mongo_doc(data):
    """
    FIX: Converteert MongoDB's ObjectId en datetime objecten in een document
    (of lijst van documenten) naar JSON-serialiseerbare strings.
    """
    if isinstance(data, list):
        return [format_mongo_doc(item) for item in data]
    
    if isinstance(data, dict):
        new_doc = {}
        for key, value in data.items():
            if isinstance(value, ObjectId):
                # Converteer ObjectId naar string
                new_doc[key] = str(value)
            elif isinstance(value, datetime.datetime):
                # Converteer datetime naar ISO string
                new_doc[key] = value.isoformat()
            elif isinstance(value, (dict, list)):
                # Recursief verwerken van geneste structuren
                new_doc[key] = format_mongo_doc(value)
            else:
                new_doc[key] = value
        
        # Optioneel: hernoem _id naar id op topniveau van het document
        if '_id' in new_doc:
            new_doc['id'] = new_doc.pop('_id')
        
        return new_doc
    
    return data
# --- Einde JSON Serialisatie FIX ---

# --- Endpoint Logica ---

def log_statistic(action, client_id, endpoint_name):
    # Log een API aanvraag
    db = get_db()
    if db is not None: 
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

# --- NIEUWE FUNCTIE: Wachtwoord Reset ---
def reset_admin_password(db):
    """Genereert een nieuw willekeurig admin wachtwoord en slaat het gehasht op."""
    new_pass = secrets.token_urlsafe(16)
    hashed_pass = hash_password(new_pass)
    
    # Update de admin gebruiker in de database
    result = db.users.update_one(
        {'username': 'admin'},
        {'$set': {'password': hashed_pass}}
    )
    
    if result.matched_count == 0:
        # Als de admin niet bestaat, maak deze dan aan (dit zou niet mogen gebeuren)
        db.users.insert_one({
            'username': 'admin',
            'password': hashed_pass,
            'role': 'admin'
        })

    print("-" * 50)
    print("!!! ADMIN WACHTWOORD GERESET !!!")
    print(f"Nieuw wachtwoord voor 'admin': {new_pass}")
    print("Log nu in met dit wachtwoord.")
    print("-" * 50)
    
# --- Statische Bestanden Serveren (voor Dashboard) ---

@app.route('/')
def serve_dashboard():
    """
    Serveert het statische dashboard.html bestand vanaf de root URL.
    """
    # De directory is de map waarin app.py draait.
    root_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(root_dir, 'dashboard.html')

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

            # FIX: Gebruik de helper om het document te serialiseren
            result = format_mongo_doc(doc)
            log_statistic("get_one", client_id, endpoint_name)
            return jsonify({"id": result['id'], "data": result}), 200
        else:
            query_params = {k: v for k, v in request.args.items() if k not in ['api_key', 'client_id']}
            
            filter_query = {'meta.client_id': client_id}
            
            for key, value in query_params.items():
                if key.startswith('meta.'):
                    filter_query[key] = value
                else:
                    filter_query[f'data.{key}'] = value

            docs = list(collection.find(filter_query, {'_id': 1, 'id': 1, 'data': 1, 'meta': 1}))
            
            # FIX: Gebruik de helper om de lijst van documenten te serialiseren
            results = format_mongo_doc(docs)

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
            
            # FIX: Serialiseer het resultaat
            serialized_doc = format_mongo_doc(new_doc)
            serialized_doc['id'] = str(result.inserted_id)
            
            return jsonify({
                "id": serialized_doc['id'], 
                "data": serialized_doc
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
        
        log_statistic("update_one", client_id, endpoint_name)
        
        # FIX: Serialiseer de updated document
        serialized_doc = format_mongo_doc(updated_doc)
        
        return jsonify({
            "id": serialized_doc['id'], 
            "data": serialized_doc
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
    if db is not None: 
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

# --- Profiel wijzigen (Wachtwoord/Gebruikersnaam) ---
@app.route('/api/admin/profile', methods=['GET', 'POST'])
@check_auth
def api_admin_profile():
    db = get_db()
    g = globals()
    user_id = g['user_id']
    
    if request.method == 'GET':
        # Haal de huidige admin info op (alleen username, geen wachtwoord hash!)
        user = db.users.find_one({'username': user_id}, {'_id': 0, 'username': 1, 'role': 1})
        if user:
            return jsonify(user)
        return jsonify({'error': 'Gebruiker niet gevonden.'}), 404

    elif request.method == 'POST':
        data = request.get_json()
        new_username = data.get('new_username')
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        
        user_doc = db.users.find_one({'username': user_id})

        if not user_doc or not check_password(old_password, user_doc['password']):
            return jsonify({'error': 'Huidig wachtwoord is onjuist.'}), 401

        update_set = {}
        
        # 1. Update Wachtwoord
        if new_password:
            if len(new_password) < 8:
                return jsonify({'error': 'Nieuw wachtwoord moet minimaal 8 tekens bevatten.'}), 400
            update_set['password'] = hash_password(new_password)

        # 2. Update Gebruikersnaam
        if new_username and new_username != user_id:
            if db.users.find_one({'username': new_username}):
                return jsonify({'error': f'Gebruikersnaam "{new_username}" is al in gebruik.'}), 400
            
            update_set['username'] = new_username
            
        if not update_set:
            return jsonify({'message': 'Geen wijzigingen aangebracht.'})
            
        # Voer de update uit
        db.users.update_one({'username': user_id}, {'$set': update_set})
        
        # Als de gebruikersnaam is gewijzigd, moet de JWT worden vernieuwd
        if 'username' in update_set:
            new_token = generate_jwt(new_username)
            resp = make_response(jsonify({'message': 'Profiel en gebruikersnaam succesvol bijgewerkt. Nieuwe login vereist.', 'new_username': new_username}), 200)
            # Wis de oude cookie
            resp.set_cookie(app.config['JWT_COOKIE_NAME'], '', expires=0, httponly=True, samesite='Lax')
            # Zet de nieuwe cookie
            resp.set_cookie(
                app.config['JWT_COOKIE_NAME'], 
                new_token, 
                httponly=True, 
                secure=app.config.get('ENV') == 'production',
                samesite='Lax',
                max_age=app.config['JWT_EXPIRY_MINUTES'] * 60
            )
            return resp
        
        return jsonify({'message': 'Profiel succesvol bijgewerkt.'})


# --- FIX: Scan Endpoints op Inaccessible Data ---
@app.route('/api/collections/scan', methods=['GET'])
@check_auth
def api_collections_scan():
    db = get_db()
    if db is None: return jsonify({"error": "Database connection error"}), 503

    g = globals()
    user_id = g['user_id']
    
    # 1. Haal alle Client ID's van de huidige admin op
    admin_client_ids = [client['_id'] for client in db.clients.find({'user_id': user_id, 'revoked': False})]
    
    system_collections = ['users', 'clients', 'statistics', 'system.indexes']
    user_endpoints = [name for name in db.list_collection_names() if name not in system_collections]
    
    collection_stats = []

    for name in user_endpoints:
        collection = db[name]
        try:
            total_count = collection.count_documents({})
            
            # 2. DEFINITIE VAN 'WEESDATA' (INACCESSIBLE DATA):
            # Documenten die NIET aan de admin toebehoren.
            orphan_filter = {
                '$or': [
                    {'meta.client_id': {'$exists': False}},          # Mist meta veld
                    {'meta.client_id': None},                         # meta veld is null
                    {'meta.client_id': {'$nin': admin_client_ids}}  # client_id is niet in de lijst van admin's IDs
                ]
            }
            
            orphan_count = collection.count_documents(orphan_filter)

            collection_stats.append({
                'name': name,
                'total_documents': total_count,
                'orphan_documents': orphan_count
            })
        except Exception as e:
            # Kan gebeuren als een collectie corrupt is of als een view wordt gebruikt
            collection_stats.append({
                'name': name,
                'error': f'Kon documenten niet tellen: {str(e)}'
            })
            
    return jsonify(collection_stats)


@app.route('/api/collections/convert', methods=['POST'])
@check_auth
def api_collections_convert():
    """
    Update alle weesdocumenten (ontoegankelijke data) in een gespecificeerde collectie met de opgegeven Client ID.
    """
    db = get_db()
    if db is None: return jsonify({"error": "Database connection error"}), 503

    g = globals()
    user_id = g['user_id']
    
    data = request.get_json()
    collection_name = data.get('collection_name')
    client_id = data.get('client_id')

    if not collection_name or not client_id:
        return jsonify({"error": "Collectie naam en Client ID zijn vereist."}), 400
    
    # 1. Valideer de Client ID
    client = db.clients.find_one({'_id': client_id, 'revoked': False})
    if not client:
        return jsonify({"error": "Ongeldige Client ID: de doel-client bestaat niet."}), 400
    
    # 2. Bepaal de collectie
    system_collections = ['users', 'clients', 'statistics', 'system.indexes']
    if collection_name in system_collections:
        return jsonify({"error": "Kan geen systeemcollectie converteren."}), 403
    
    collection = db[collection_name]
    
    # 3. Bepaal de 'Inaccessible Data' filter (Moet overeenkomen met de scan logica)
    admin_client_ids = [c['_id'] for c in db.clients.find({'user_id': user_id, 'revoked': False})]
    
    inaccessible_filter = {
        '$or': [
            {'meta.client_id': {'$exists': False}},
            {'meta.client_id': None},
            # Target de oude 'sandman' data of andere Client IDs die niet aan de admin toebehoren
            {'meta.client_id': {'$nin': admin_client_ids}} 
        ]
    }
    
    # Update operatie: zet meta.client_id en meta.updated_at
    update_operation = {
        '$set': {
            'meta.client_id': client_id,
            'meta.updated_at': datetime.datetime.utcnow()
        }
    }
    
    try:
        # update_many voert de conversie uit
        result = collection.update_many(inaccessible_filter, update_operation)

        return jsonify({
            'message': f'{result.modified_count} documenten in collectie "{collection_name}" zijn geconverteerd en toegewezen aan Client ID "{client_id}".',
            'modified_count': result.modified_count
        })
    except Exception as e:
        return jsonify({"error": f"Fout bij conversie: {str(e)}"}), 500


@app.route('/api/dashboard', methods=['GET'])
@check_auth
def api_dashboard():
    db = get_db()
    g = globals()
    user_id = g['user_id']
    
    # Haal Top 10 statistieken op
    pipeline = [
        {'$group': {'_id': '$endpoint', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 10}
    ]
    endpoint_stats = list(db.statistics.aggregate(pipeline))
    
    # Haal recente activiteit op
    recent_activity = list(db.statistics.find().sort('timestamp', -1).limit(20))
    
    # Haal alle collecties op
    collection_names = db.list_collection_names()
    
    # Definieer de systeem/interne collecties
    system_collections = ['users', 'clients', 'statistics', 'system.indexes']
    
    # Bereken het aantal actieve (user) endpoints
    user_endpoints = [name for name in collection_names if name not in system_collections]
    total_endpoints = len(user_endpoints)
    total_clients = db.clients.count_documents({})
    total_calls = db.statistics.count_documents({})

    # FIX: Serialiseer alle data voor de respons
    serialized_endpoint_stats = format_mongo_doc(endpoint_stats)
    serialized_recent_activity = format_mongo_doc(recent_activity)
    
    # Haal de lijst van clients op voor de frontend selector (de keys zijn hier niet nodig)
    clients = list(db.clients.find({'user_id': user_id, 'revoked': False}, {'_id': 1, 'description': 1}))
    
    serialized_clients = format_mongo_doc(clients)

    return jsonify({
        'user_id': user_id,
        'summary': {
            'endpoints_count': total_endpoints,
            'clients_count': total_clients,
            'calls_count': total_calls
        },
        'top_endpoints': serialized_endpoint_stats,
        'recent_activity': serialized_recent_activity,
        'all_collections': user_endpoints,
        'available_clients_meta': serialized_clients
    })


@app.route('/api/settings', methods=['GET', 'POST', 'DELETE'])
@check_auth
def api_settings():
    db = get_db()
    g = globals()
    user_id = g['user_id']
    
    if request.method == 'GET':
        api_keys = []
        # FIX: Serialiseer de client data hier om ObjectId in _id en de datetime te fixen
        for client in db.clients.find({'user_id': user_id, 'revoked': False}):
            client_data = format_mongo_doc(client) # Gebruik de helper
            api_keys.append({
                'client_id': client_data['id'], 
                'key': client_data['key'], 
                'description': client_data.get('description', 'N/A'),
                'created_at': client_data['created_at']
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
    
    # 1. Controleer of de gebruiker de reset wil uitvoeren
    # Gebruik sys.argv om te controleren op een argument
    if len(sys.argv) > 1 and sys.argv[1] == 'reset-pass':
        if db is not None:
            reset_admin_password(db)
        # Stop de app na de reset (omdat we alleen het wachtwoord wilden weten)
        sys.exit(0) 

    # 2. Normale start
    if db is not None: 
        create_initial_admin(db)
        
    # Start de Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)
