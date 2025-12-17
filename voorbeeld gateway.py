import os
import datetime
from functools import wraps
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId

app = Flask(__name__)
# CORS staat alles toe. De werkelijke toegangscontrole wordt gedaan door de Reverse Proxy 
# die de x-client-id header injecteert op basis van authenticatie aan de rand van het netwerk.
CORS(app, resources={r"/*": {"origins": "*"}})

# MongoDB Configuratie: 'mongo' is de servicenaam in de Docker-omgeving.
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongo:27017/')

def get_db():
    """Verbinding met MongoDB met een korte timeout om blokkades te voorkomen."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        return client['data_store']
    except Exception as e:
        print(f"DATABASE ERROR: {e}")
        return None

def require_client_id(f):
    """
    DECORATOR: Garandeert dat elk verzoek een eigenaar (client_id) heeft.
    In de architectuur wordt dit ID meestal door de Reverse Proxy (bijv. Nginx/Traefik) 
    meegestuurd nadat de gebruiker is geïdentificeerd en anders door de client zelf toegevoegd.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_id = request.headers.get('x-client-id') or request.args.get('client_id')
        if not client_id:
            return jsonify({"error": "Missing x-client-id header. Toegang geweigerd."}), 400
        g.client_id = client_id
        return f(*args, **kwargs)
    return decorated_function

def format_doc(doc):
    """
    TRANSFORMATIE: Van Database naar Client (Export).
    De Gateway bewaart metadata in een '_meta' container om conflicten te voorkomen.
    Bij het terugsturen naar de client worden deze velden 'platgeslagen' met een underscore.
    
    Voorbeeld output voor de client:
    {
       "_id": "...", 
       "_client_id": "user123", 
       "_created_at": "2025-01-01...", 
       "jouw_veld": "waarde"
    }
    """
    if isinstance(doc, list):
        return [format_doc(d) for d in doc]
    if isinstance(doc, dict):
        new_doc = {}
        for k, v in doc.items():
            if k == '_id':
                new_doc['_id'] = str(v)
            elif k == '_meta':
                # Systeemvelden krijgen een underscore prefix voor de client
                new_doc['_client_id'] = v.get('owner')
                if v.get('created_at'):
                    new_doc['_created_at'] = v.get('created_at').isoformat()
                if v.get('updated_at'):
                    new_doc['_updated_at'] = v.get('updated_at').isoformat()
            else:
                # Pure gebruikersdata blijft ongewijzigd
                new_doc[k] = v
        return new_doc
    return doc

def clean_incoming_data(data):
    """
    VEILIGHEID: Opschonen van inkomende data (Import).
    Clients mogen geen velden sturen die beginnen met een '_'. 
    Deze velden zijn gereserveerd voor de Gateway (zoals _client_id). 
    Door deze te filteren, kan een client nooit zijn eigen eigenaarschap of 
    aanmaakdatum vervalsen.
    """
    if not isinstance(data, dict): return data
    return {k: v for k, v in data.items() if not k.startswith('_')}

# --- API GATEWAY ROUTES ---

@app.route('/api/<collection_name>', methods=['GET', 'POST'])
@require_client_id
def api_collection(collection_name):
    """
    Beheert collecties.
    GET: Haalt alle documenten op die eigendom zijn van de huidige client.
    POST: Slaat nieuwe data op en verzegelt deze met eigenaars-metadata.
    """
    db = get_db()
    if db is None: return jsonify({"error": "Database Offline"}), 503
    col = db[collection_name]
    
    if request.method == 'GET':
        # Haal alleen data op waarbij de interne _meta.owner matcht met de x-client-id
        docs = list(col.find({'_meta.owner': g.client_id}))
        return jsonify(format_doc(docs)), 200

    if request.method == 'POST':
        raw_data = request.get_json(silent=True) or {}
        
        # Stap 1: Filter velden met '_' (voorkom vervalsing van metadata)
        user_data = clean_incoming_data(raw_data)
        
        # Stap 2: Voeg de onschendbare systeemcontainer toe
        user_data['_meta'] = {
            'owner': g.client_id,
            'created_at': datetime.datetime.utcnow()
        }
        
        result = col.insert_one(user_data)
        return jsonify({"_id": str(result.inserted_id), "status": "created"}), 201

@app.route('/api/<collection_name>/<doc_id>', methods=['GET', 'PUT', 'DELETE'])
@require_client_id
def api_document(collection_name, doc_id):
    """
    Beheert individuele documenten op basis van ID.
    Controleert bij elke actie of de client de rechtmatige eigenaar is via _meta.owner.
    """
    db = get_db()
    if db is None: return jsonify({"error": "Database Offline"}), 503
    col = db[collection_name]
    
    try: q_id = ObjectId(doc_id)
    except: q_id = doc_id # Support voor non-objectid keys
    
    # De query garandeert 'Isolatie': Je kunt nooit data van een ander ID aanpassen/lezen.
    query = {'_id': q_id, '_meta.owner': g.client_id}

    if request.method == 'GET':
        doc = col.find_one(query)
        return (jsonify(format_doc(doc)), 200) if doc else (jsonify({"error": "Niet gevonden of geen toegang"}), 404)

    if request.method == 'PUT':
        raw_data = request.get_json(silent=True) or {}
        user_data = clean_incoming_data(raw_data) # Filter '_' velden
        
        # Update user data en werk de systeem-timestamp bij
        res = col.update_one(query, {
            '$set': user_data,
            '$set': {'_meta.updated_at': datetime.datetime.utcnow()}
        })
        return jsonify({"status": "updated" if res.matched_count else "not found"}), 200

    if request.method == 'DELETE':
        res = col.delete_one(query)
        return jsonify({"status": "deleted" if res.deleted_count else "not found"}), 200

# --- DASHBOARD & SYSTEEM ROUTES ---

@app.route('/dashboard_data')
def dashboard_data():
    """Geeft systeemoverzicht voor het beheerpaneel."""
    db = get_db()
    if db is None: return jsonify({'error': 'DB Offline'}), 500
    
    cols = db.list_collection_names()
    # Filter systeemcollecties eruit voor het overzicht
    endpoints = [c for c in cols if c not in ['clients', 'statistics', 'system.indexes']]
    clients = list(db.clients.find({}, {'description': 1, '_id': 1}))

    return jsonify({
        'stats': { 'active_endpoints': len(endpoints), 'known_clients': len(clients) },
        'clients': format_doc(clients),
        'endpoints': endpoints
    })

if __name__ == '__main__':
    # Flask start op poort 5000. 
    # In productie draait dit achter een Gunicorn/Nginx setup.
    app.run(host='0.0.0.0', port=5000, debug=True)
