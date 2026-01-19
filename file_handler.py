import os
import datetime
from flask import Blueprint, request, jsonify, send_from_directory, current_app, url_for
from werkzeug.utils import secure_filename

# Maak een Blueprint aan
file_bp = Blueprint('file_handler', __name__)

# Configuratie: Waar slaan we de bestanden op?
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'local_storage')

# Zorg dat de basis map bestaat bij het opstarten
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename

@file_bp.route('/<ep_name>/files', methods=['POST'])
def upload_file(ep_name):
    """
    Endpoint om een bestand te uploaden voor een specifieke endpoint/collectie.
    URL: POST /api/<ep_name>/files
    """
    client_id = request.headers.get('x-client-id') or request.args.get('client_id')
    if not client_id:
        return jsonify({"error": "Missing x-client-id header"}), 400

    if 'file' not in request.files:
        return jsonify({"error": "No file part in request"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        filename = secure_filename(file.filename)
        
        # Gebruik ep_name en client_id voor de mappenstructuur
        # local_storage/<ep_name>/<client_id>/<filename>
        target_dir = os.path.join(UPLOAD_FOLDER, ep_name, client_id)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
            
        save_path = os.path.join(target_dir, filename)
        
        try:
            file.save(save_path)
            # Genereer de URL voor het ophalen van het bestand
            # We noemen het nu ep_name in de route om conflict met url_for(endpoint=...) te voorkomen
            download_url = url_for('file_handler.get_file', 
                                   ep_name=ep_name, 
                                   filename=filename, 
                                   _external=True)
            
            if '?' not in download_url:
                download_url += f"?client_id={client_id}"
            else:
                download_url += f"&client_id={client_id}"

            return jsonify({
                "status": "stored", 
                "endpoint": ep_name,
                "filename": filename, 
                "url": download_url
            }), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@file_bp.route('/<ep_name>/files/<path:filename>', methods=['GET'])
def get_file(ep_name, filename):
    """
    Endpoint om een bestand op te halen voor een specifieke endpoint en client.
    URL: GET /api/<ep_name>/files/<filename>
    """
    client_id = request.headers.get('x-client-id') or request.args.get('client_id')
    if not client_id:
        return jsonify({"error": "Missing x-client-id header or client_id param"}), 400
        
    client_dir = os.path.join(UPLOAD_FOLDER, ep_name, client_id)
    try:
        return send_from_directory(client_dir, filename)
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

@file_bp.route('/admin/files/<ep_name>', methods=['GET'])
def admin_list_files(ep_name):
    """
    (ADMIN) Lijst alle bestanden in een file endpoint, gegroepeerd per client.
    """
    endpoint_path = os.path.join(UPLOAD_FOLDER, ep_name)
    
    if not os.path.exists(endpoint_path):
        return jsonify([])
        
    all_files = []
    for client_id in os.listdir(endpoint_path):
        client_path = os.path.join(endpoint_path, client_id)
        if os.path.isdir(client_path):
            for filename in os.listdir(client_path):
                file_path = os.path.join(client_path, filename)
                stats = os.stat(file_path)
                all_files.append({
                    'filename': filename,
                    'client_id': client_id,
                    'size': stats.st_size,
                    'created_at': datetime.datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    'url': f"/api/{ep_name}/files/{filename}?client_id={client_id}"
                })
    return jsonify(all_files)

@file_bp.route('/admin/files/<ep_name>/<client_id>/<path:filename>', methods=['DELETE'])
def admin_delete_file(ep_name, client_id, filename):
    """
    (ADMIN) Verwijder een bestand.
    """
    file_path = os.path.join(UPLOAD_FOLDER, ep_name, client_id, filename)
    
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({"status": "deleted"})
    return jsonify({"error": "File not found"}), 404
