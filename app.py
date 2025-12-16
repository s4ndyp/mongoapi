import os
import json
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, send_file, flash
from pymongo import MongoClient
from bson import ObjectId, json_util
from datetime import datetime
import io

app = Flask(__name__)
app.secret_key = 'supersecretkey_change_this'  # Nodig voor flash messages

# ------------------------------------------------------------------------------
# CONFIGURATIE & DATABASE VERBINDING
# ------------------------------------------------------------------------------
# Pas deze URI aan naar jouw MongoDB server
MONGO_URI = 'mongodb://localhost:27017/'
client = MongoClient(MONGO_URI)
db = client['api_gateway_v2']  # Nieuwe database naam voor V2 structuur

# Collectie voor de configuratie van endpoints (metadata)
# Document structuur: { "app_name":Str, "endpoint_name":Str, "description":Str, "created_at": Date }
endpoints_meta = db['system_endpoints']

# ------------------------------------------------------------------------------
# HULPFUNCTIES
# ------------------------------------------------------------------------------

def get_data_collection_name(app_name, endpoint_name):
    """Genereert de collectienaam voor de data opslag: data_<app>_<endpoint>"""
    # Zorg dat namen veilig zijn voor mongodb collecties (geen vreemde tekens)
    safe_app = "".join(x for x in app_name if x.isalnum() or x in "_-")
    safe_end = "".join(x for x in endpoint_name if x.isalnum() or x in "_-")
    return f"data_{safe_app}_{safe_end}"

def serialize_doc(doc):
    """Zet MongoDB document om naar JSON-serializable formaat"""
    if not doc:
        return None
    doc['id'] = str(doc['_id'])
    del doc['_id']
    return doc

# ------------------------------------------------------------------------------
# FRONTEND / DASHBOARD ROUTES
# ------------------------------------------------------------------------------

@app.route('/')
def dashboard():
    """Toont het dashboard met sidebar en endpoints."""
    # Haal filter op uit URL (bijv: /?app=MijnApp)
    selected_app = request.args.get('app')
    
    # Haal alle unieke applicatie namen op voor de sidebar
    all_metas = list(endpoints_meta.find().sort("app_name", 1))
    unique_apps = sorted(list(set([m['app_name'] for m in all_metas])))
    
    # Filter endpoints voor de view
    if selected_app:
        filtered_endpoints = [m for m in all_metas if m['app_name'] == selected_app]
    else:
        filtered_endpoints = all_metas # "Alles" geselecteerd
        
    # Voeg statistieken toe (aantal documenten per endpoint)
    for ep in filtered_endpoints:
        col_name = get_data_collection_name(ep['app_name'], ep['endpoint_name'])
        ep['doc_count'] = db[col_name].count_documents({})
        ep['collection_name'] = col_name

    return render_template_string(HTML_TEMPLATE, 
                                  apps=unique_apps, 
                                  endpoints=filtered_endpoints, 
                                  selected_app=selected_app)

# ------------------------------------------------------------------------------
# API ROUTES (DYNAMISCH)
# ------------------------------------------------------------------------------

@app.route('/api/<app_name>/<endpoint_name>', methods=['GET', 'POST', 'DELETE'])
def handle_endpoint(app_name, endpoint_name):
    """
    Dynamische route voor: /api/<app>/<endpoint>
    GET: Haal alle data op
    POST: Voeg nieuwe data toe
    DELETE: Verwijder de hele collectie (pas op!)
    """
    # Check of endpoint bestaat in metadata
    meta = endpoints_meta.find_one({"app_name": app_name, "endpoint_name": endpoint_name})
    if not meta:
        return jsonify({"error": f"Endpoint '/api/{app_name}/{endpoint_name}' not defined."}), 404
    
    col_name = get_data_collection_name(app_name, endpoint_name)
    collection = db[col_name]

    if request.method == 'GET':
        data = list(collection.find())
        return jsonify([serialize_doc(doc) for doc in data]), 200

    elif request.method == 'POST':
        payload = request.json
        if not payload:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Voeg timestamp toe indien niet aanwezig
        if isinstance(payload, dict) and "created_at" not in payload:
            payload["created_at"] = datetime.utcnow()
        
        result = collection.insert_one(payload)
        return jsonify({"message": "Created", "id": str(result.inserted_id)}), 201
    
    elif request.method == 'DELETE':
        # Let op: Dit verwijdert ALLE data in dit endpoint, maar behoudt de definitie
        collection.delete_many({})
        return jsonify({"message": "All data cleared from endpoint"}), 200


@app.route('/api/<app_name>/<endpoint_name>/<doc_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_document(app_name, endpoint_name, doc_id):
    """
    Dynamische route voor specifiek document: /api/<app>/<endpoint>/<id>
    """
    meta = endpoints_meta.find_one({"app_name": app_name, "endpoint_name": endpoint_name})
    if not meta:
        return jsonify({"error": "Endpoint not found"}), 404

    col_name = get_data_collection_name(app_name, endpoint_name)
    collection = db[col_name]
    
    try:
        oid = ObjectId(doc_id)
    except:
        return jsonify({"error": "Invalid ID format"}), 400

    if request.method == 'GET':
        doc = collection.find_one({"_id": oid})
        if not doc:
            return jsonify({"error": "Document not found"}), 404
        return jsonify(serialize_doc(doc))

    elif request.method == 'PUT':
        payload = request.json
        if not payload:
            return jsonify({"error": "No data"}), 400
        
        # update_one met $set zorgt dat we velden updaten, niet het hele doc overschrijven (tenzij gewenst)
        # Hier vervangen we de inhoud behalve _id
        collection.replace_one({"_id": oid}, payload)
        return jsonify({"message": "Updated", "id": doc_id})

    elif request.method == 'DELETE':
        result = collection.delete_one({"_id": oid})
        if result.deleted_count == 0:
            return jsonify({"error": "Document not found"}), 404
        return jsonify({"message": "Deleted", "id": doc_id})

# ------------------------------------------------------------------------------
# BEHEER ROUTES (Create, Rename, Import, Export)
# ------------------------------------------------------------------------------

@app.route('/manage/add', methods=['POST'])
def add_endpoint():
    app_name = request.form.get('app_name')
    endpoint_name = request.form.get('endpoint_name')
    description = request.form.get('description', '')

    if not app_name or not endpoint_name:
        flash("Applicatie naam en Endpoint naam zijn verplicht!", "error")
        return redirect(url_for('dashboard'))

    # Check dubbele
    exists = endpoints_meta.find_one({"app_name": app_name, "endpoint_name": endpoint_name})
    if exists:
        flash("Dit endpoint bestaat al voor deze applicatie.", "error")
        return redirect(url_for('dashboard'))

    endpoints_meta.insert_one({
        "app_name": app_name,
        "endpoint_name": endpoint_name,
        "description": description,
        "created_at": datetime.utcnow()
    })
    
    flash(f"Endpoint /api/{app_name}/{endpoint_name} aangemaakt.", "success")
    return redirect(url_for('dashboard', app=app_name))

@app.route('/manage/delete', methods=['POST'])
def delete_endpoint():
    """Verwijdert definitie EN data collectie"""
    app_name = request.form.get('app_name')
    endpoint_name = request.form.get('endpoint_name')

    col_name = get_data_collection_name(app_name, endpoint_name)
    
    # Drop data collectie
    db[col_name].drop()
    
    # Verwijder metadata
    endpoints_meta.delete_one({"app_name": app_name, "endpoint_name": endpoint_name})
    
    flash(f"Endpoint {app_name}/{endpoint_name} en alle data verwijderd.", "success")
    return redirect(url_for('dashboard'))

@app.route('/manage/rename_app', methods=['POST'])
def rename_application():
    old_app_name = request.form.get('old_app_name')
    new_app_name = request.form.get('new_app_name')
    
    if not old_app_name or not new_app_name:
        flash("Namen mogen niet leeg zijn", "error")
        return redirect(url_for('dashboard'))

    # Zoek alle endpoints van deze app
    endpoints = list(endpoints_meta.find({"app_name": old_app_name}))
    
    count = 0
    for ep in endpoints:
        old_col = get_data_collection_name(old_app_name, ep['endpoint_name'])
        new_col = get_data_collection_name(new_app_name, ep['endpoint_name'])
        
        # 1. Hernoem MongoDB collectie (indien data bestaat)
        if old_col in db.list_collection_names():
            try:
                db[old_col].rename(new_col)
            except Exception as e:
                flash(f"Fout bij hernoemen data: {e}", "error")
        
        # 2. Update metadata
        endpoints_meta.update_one(
            {"_id": ep["_id"]}, 
            {"$set": {"app_name": new_app_name}}
        )
        count += 1
        
    flash(f"Applicatie '{old_app_name}' hernoemd naar '{new_app_name}'. {count} endpoints bijgewerkt.", "success")
    return redirect(url_for('dashboard', app=new_app_name))

@app.route('/manage/rename_endpoint', methods=['POST'])
def rename_endpoint_route():
    app_name = request.form.get('app_name')
    old_ep_name = request.form.get('old_endpoint_name')
    new_ep_name = request.form.get('new_endpoint_name')
    
    # Check of nieuwe naam al bestaat
    if endpoints_meta.find_one({"app_name": app_name, "endpoint_name": new_ep_name}):
        flash("Nieuwe naam bestaat al binnen deze applicatie.", "error")
        return redirect(url_for('dashboard', app=app_name))

    old_col = get_data_collection_name(app_name, old_ep_name)
    new_col = get_data_collection_name(app_name, new_ep_name)

    # 1. Hernoem collectie
    if old_col in db.list_collection_names():
        db[old_col].rename(new_col)
    
    # 2. Update metadata
    endpoints_meta.update_one(
        {"app_name": app_name, "endpoint_name": old_ep_name},
        {"$set": {"endpoint_name": new_ep_name}}
    )

    flash(f"Endpoint hernoemd naar {new_ep_name}", "success")
    return redirect(url_for('dashboard', app=app_name))

@app.route('/manage/export/<app_name>/<endpoint_name>')
def export_data(app_name, endpoint_name):
    col_name = get_data_collection_name(app_name, endpoint_name)
    data = list(db[col_name].find())
    
    # Gebruik json_util voor correcte conversie van ObjectId en Dates
    json_str = json_util.dumps(data, indent=2)
    
    return send_file(
        io.BytesIO(json_str.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f"{app_name}_{endpoint_name}_backup.json"
    )

@app.route('/manage/import/<app_name>/<endpoint_name>', methods=['POST'])
def import_data(app_name, endpoint_name):
    if 'file' not in request.files:
        flash("Geen bestand geselecteerd", "error")
        return redirect(url_for('dashboard', app=app_name))
        
    file = request.files['file']
    if file.filename == '':
        flash("Geen bestand geselecteerd", "error")
        return redirect(url_for('dashboard', app=app_name))

    try:
        data = json_util.loads(file.read())
        if not isinstance(data, list):
            flash("JSON bestand moet een lijst van documenten zijn.", "error")
            return redirect(url_for('dashboard', app=app_name))
        
        col_name = get_data_collection_name(app_name, endpoint_name)
        
        # Schoon _id's op om conflicten te voorkomen bij insert (of gebruik save logica)
        # Hier kiezen we voor toevoegen. Als je wilt overschrijven, moet je eerst droppen.
        clean_data = []
        for doc in data:
            if "_id" in doc:
                del doc["_id"] # Laat Mongo nieuwe ID's genereren om collisions te voorkomen
            clean_data.append(doc)
            
        if clean_data:
            db[col_name].insert_many(clean_data)
            
        flash(f"{len(clean_data)} documenten succesvol geïmporteerd.", "success")
    except Exception as e:
        flash(f"Fout bij importeren: {str(e)}", "error")

    return redirect(url_for('dashboard', app=app_name))


# ------------------------------------------------------------------------------
# UI TEMPLATES (HTML/CSS)
# ------------------------------------------------------------------------------
# In een productieomgeving zou je dit in templates/index.html en static/styles.css zetten.
# Voor nu zit alles hierin voor 1-file deployment.

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Gateway Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --primary-color: #2563eb;
            --secondary-color: #64748b;
            --background-color: #f8fafc;
            --sidebar-bg: #1e293b;
            --sidebar-text: #e2e8f0;
            --card-bg: #ffffff;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --border-color: #e2e8f0;
            --success: #22c55e;
            --danger: #ef4444;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: var(--background-color); color: var(--text-primary); display: flex; height: 100vh; overflow: hidden; }

        /* Sidebar */
        .sidebar { width: 280px; background: var(--sidebar-bg); color: var(--sidebar-text); display: flex; flex-direction: column; padding: 1.5rem; transition: all 0.3s ease; }
        .sidebar-header { margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #334155; }
        .logo { font-size: 1.5rem; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 0.75rem; }
        
        .nav-section { margin-bottom: 2rem; }
        .nav-title { text-transform: uppercase; font-size: 0.75rem; font-weight: 600; color: #94a3b8; margin-bottom: 0.75rem; letter-spacing: 0.05em; }
        .nav-item { display: flex; align-items: center; padding: 0.75rem 1rem; color: #cbd5e1; text-decoration: none; border-radius: 0.5rem; transition: all 0.2s; margin-bottom: 0.25rem; }
        .nav-item:hover, .nav-item.active { background: #334155; color: #fff; transform: translateX(4px); }
        .nav-item i { width: 20px; margin-right: 0.75rem; }

        /* Main Content */
        .main-content { flex: 1; overflow-y: auto; padding: 2rem; background: var(--background-color); }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
        .page-title h1 { font-size: 1.8rem; font-weight: 600; color: var(--text-primary); }
        .page-title p { color: var(--text-secondary); margin-top: 0.25rem; }
        
        .btn { padding: 0.6rem 1.2rem; border-radius: 0.5rem; border: none; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 0.5rem; transition: all 0.2s; text-decoration: none; font-size: 0.9rem; }
        .btn-primary { background: var(--primary-color); color: white; }
        .btn-primary:hover { background: #1d4ed8; }
        .btn-danger { background: var(--danger); color: white; }
        .btn-sm { padding: 0.4rem 0.8rem; font-size: 0.8rem; }
        .btn-ghost { background: transparent; color: var(--text-secondary); border: 1px solid var(--border-color); }
        .btn-ghost:hover { background: #f1f5f9; color: var(--text-primary); }

        /* Grid & Cards */
        .grid-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem; }
        .card { background: var(--card-bg); border-radius: 1rem; padding: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); border: 1px solid var(--border-color); transition: transform 0.2s, box-shadow 0.2s; }
        .card:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05); }
        
        .card-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 1rem; }
        .method-badge { background: #dbeafe; color: #1e40af; padding: 0.25rem 0.6rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 600; }
        .card-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }
        .card-path { font-family: 'Monaco', 'Consolas', monospace; font-size: 0.85rem; color: var(--text-secondary); background: #f1f5f9; padding: 0.25rem 0.5rem; border-radius: 0.25rem; word-break: break-all; }
        
        .stat-row { display: flex; gap: 1.5rem; margin: 1rem 0; padding: 1rem 0; border-top: 1px solid #f1f5f9; border-bottom: 1px solid #f1f5f9; }
        .stat-item { display: flex; flex-direction: column; }
        .stat-label { font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; }
        .stat-value { font-weight: 600; color: var(--text-primary); }

        .card-actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 1rem; }

        /* Forms & Modals */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; align-items: center; justify-content: center; }
        .modal.active { display: flex; }
        .modal-content { background: white; padding: 2rem; border-radius: 1rem; width: 100%; max-width: 500px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1); }
        .modal-header { display: flex; justify-content: space-between; margin-bottom: 1.5rem; }
        .modal-title { font-size: 1.25rem; font-weight: 600; }
        .close-modal { cursor: pointer; font-size: 1.5rem; color: var(--text-secondary); }
        
        .form-group { margin-bottom: 1.25rem; }
        .form-label { display: block; margin-bottom: 0.5rem; font-weight: 500; font-size: 0.9rem; }
        .form-input { width: 100%; padding: 0.75rem; border: 1px solid var(--border-color); border-radius: 0.5rem; font-family: inherit; transition: border-color 0.2s; }
        .form-input:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1); }

        .flash-messages { margin-bottom: 1.5rem; }
        .alert { padding: 1rem; border-radius: 0.5rem; margin-bottom: 0.5rem; font-size: 0.9rem; }
        .alert-error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .alert-success { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }

        .app-header-actions { display: flex; gap: 10px; align-items: center; }
        .edit-icon { color: var(--text-secondary); cursor: pointer; font-size: 0.9rem; margin-left: 8px; }
        .edit-icon:hover { color: var(--primary-color); }
    </style>
</head>
<body>

    <aside class="sidebar">
        <div class="sidebar-header">
            <div class="logo">
                <i class="fas fa-network-wired"></i>
                <span>API Gateway</span>
            </div>
        </div>

        <div class="nav-section">
            <div class="nav-title">Overzicht</div>
            <a href="/" class="nav-item {{ 'active' if not selected_app else '' }}">
                <i class="fas fa-th-large"></i> Alles
            </a>
        </div>

        <div class="nav-section">
            <div class="nav-title">Applicaties</div>
            {% for app in apps %}
            <a href="/?app={{ app }}" class="nav-item {{ 'active' if selected_app == app else '' }}">
                <i class="fas fa-layer-group"></i> {{ app }}
            </a>
            {% endfor %}
        </div>
    </aside>

    <main class="main-content">
        
        <div class="header">
            <div class="page-title">
                <div class="app-header-actions">
                    <h1>
                        {% if selected_app %}{{ selected_app }}{% else %}Alle Endpoints{% endif %}
                    </h1>
                    {% if selected_app %}
                    <i class="fas fa-pencil-alt edit-icon" onclick="openRenameAppModal('{{ selected_app }}')" title="Applicatie hernoemen"></i>
                    {% endif %}
                </div>
                <p>Beheer je API connecties en data opslag</p>
            </div>
            <button class="btn btn-primary" onclick="openModal('addEndpointModal')">
                <i class="fas fa-plus"></i> Nieuw Endpoint
            </button>
        </div>

        <div class="flash-messages">
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                  <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}
        </div>

        <div class="grid-container">
            {% for ep in endpoints %}
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <i class="fas fa-database" style="color: var(--primary-color);"></i>
                        {{ ep.endpoint_name }}
                    </div>
                    <span class="method-badge">REST</span>
                </div>
                
                <div class="card-path">/api/{{ ep.app_name }}/{{ ep.endpoint_name }}</div>
                
                <div class="stat-row">
                    <div class="stat-item">
                        <span class="stat-label">Documenten</span>
                        <span class="stat-value">{{ ep.doc_count }}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Aangemaakt</span>
                        <span class="stat-value">{{ ep.created_at.strftime('%d-%m-%Y') if ep.created_at else '-' }}</span>
                    </div>
                </div>

                <p style="font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 1rem;">
                    {{ ep.description }}
                </p>

                <div class="card-actions">
                    <a href="/manage/export/{{ ep.app_name }}/{{ ep.endpoint_name }}" class="btn btn-ghost btn-sm" title="Export JSON">
                        <i class="fas fa-download"></i>
                    </a>
                    <button class="btn btn-ghost btn-sm" onclick="openImportModal('{{ ep.app_name }}', '{{ ep.endpoint_name }}')" title="Import JSON">
                        <i class="fas fa-upload"></i>
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="openRenameEndpointModal('{{ ep.app_name }}', '{{ ep.endpoint_name }}')" title="Hernoem">
                        <i class="fas fa-edit"></i>
                    </button>
                    <form action="/manage/delete" method="POST" onsubmit="return confirm('Weet je zeker dat je dit endpoint en ALLE data wilt verwijderen?');" style="display:inline;">
                        <input type="hidden" name="app_name" value="{{ ep.app_name }}">
                        <input type="hidden" name="endpoint_name" value="{{ ep.endpoint_name }}">
                        <button type="submit" class="btn btn-ghost btn-sm" style="color: var(--danger);" title="Verwijder">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </form>
                </div>
            </div>
            {% else %}
            <div style="grid-column: 1/-1; text-align: center; padding: 4rem; color: var(--text-secondary);">
                <i class="fas fa-cubes" style="font-size: 3rem; margin-bottom: 1rem; color: #cbd5e1;"></i>
                <p>Nog geen endpoints gevonden. Maak er eentje aan!</p>
            </div>
            {% endfor %}
        </div>
    </main>

    <div id="addEndpointModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">Nieuw Endpoint</h3>
                <span class="close-modal" onclick="closeModal('addEndpointModal')">&times;</span>
            </div>
            <form action="/manage/add" method="POST">
                <div class="form-group">
                    <label class="form-label">Applicatie Naam</label>
                    <input type="text" name="app_name" class="form-input" placeholder="bv. KlantenPortaal" value="{{ selected_app if selected_app else '' }}" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Endpoint Naam</label>
                    <input type="text" name="endpoint_name" class="form-input" placeholder="bv. data" value="data" required>
                    <small style="color: var(--text-secondary);">Standaard '/data'</small>
                </div>
                <div class="form-group">
                    <label class="form-label">Beschrijving</label>
                    <input type="text" name="description" class="form-input" placeholder="Korte omschrijving">
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">Aanmaken</button>
            </form>
        </div>
    </div>

    <div id="renameAppModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">Applicatie Hernoemen</h3>
                <span class="close-modal" onclick="closeModal('renameAppModal')">&times;</span>
            </div>
            <p style="margin-bottom: 1rem; font-size: 0.9rem; color: var(--danger);">
                <i class="fas fa-exclamation-triangle"></i> Let op: Dit hernoemt ook de collecties in de database. De API URL zal veranderen.
            </p>
            <form action="/manage/rename_app" method="POST">
                <input type="hidden" name="old_app_name" id="rename_old_app_name">
                <div class="form-group">
                    <label class="form-label">Nieuwe Naam</label>
                    <input type="text" name="new_app_name" class="form-input" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">Hernoemen</button>
            </form>
        </div>
    </div>

    <div id="renameEndpointModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">Endpoint Hernoemen</h3>
                <span class="close-modal" onclick="closeModal('renameEndpointModal')">&times;</span>
            </div>
            <form action="/manage/rename_endpoint" method="POST">
                <input type="hidden" name="app_name" id="rename_ep_app_name">
                <input type="hidden" name="old_endpoint_name" id="rename_ep_old_name">
                <div class="form-group">
                    <label class="form-label">Nieuwe Endpoint Naam</label>
                    <input type="text" name="new_endpoint_name" class="form-input" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">Opslaan</button>
            </form>
        </div>
    </div>

    <div id="importModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">Import Data</h3>
                <span class="close-modal" onclick="closeModal('importModal')">&times;</span>
            </div>
            <form action="" method="POST" enctype="multipart/form-data" id="importForm">
                <div class="form-group">
                    <label class="form-label">Selecteer JSON bestand</label>
                    <input type="file" name="file" class="form-input" accept=".json" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">Upload & Import</button>
            </form>
        </div>
    </div>

    <script>
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
        
        // Sluit modals als je ernaast klikt
        window.onclick = function(event) {
            if (event.target.classList.contains('modal')) {
                event.target.classList.remove('active');
            }
        }

        function openRenameAppModal(appName) {
            document.getElementById('rename_old_app_name').value = appName;
            openModal('renameAppModal');
        }

        function openRenameEndpointModal(appName, epName) {
            document.getElementById('rename_ep_app_name').value = appName;
            document.getElementById('rename_ep_old_name').value = epName;
            openModal('renameEndpointModal');
        }

        function openImportModal(appName, epName) {
            // Zet de action van het formulier dynamisch
            const form = document.getElementById('importForm');
            form.action = `/manage/import/${appName}/${epName}`;
            openModal('importModal');
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    # Start de server
    app.run(host='0.0.0.0', port=5000, debug=True)
