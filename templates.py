# templates.py

# ------------------------------------------------------------------------------
# 1. BASE LAYOUT & Setup Content (Gewijzigd: | safe filter toegevoegd)
# ------------------------------------------------------------------------------
BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <title>{{ title }} - API Gateway V2</title>
    <meta charset="UTF-8">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root { --primary: #3b82f6; --bg: #0f172a; --card: #1e293b; --text: #f1f5f9; --text-muted: #94a3b8; --border: #334155; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }

        /* Sidebar */
        .sidebar { width: 260px; background: var(--card); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: 1.5rem; }
        .logo { font-size: 1.3rem; font-weight: 700; color: #fff; margin-bottom: 2rem; display: flex; align-items: center; gap: 10px; }
        .nav-item { display: flex; align-items: center; padding: 0.75rem 1rem; color: var(--text-muted); text-decoration: none; border-radius: 0.5rem; margin-bottom: 0.25rem; transition: 0.2s; }
        .nav-item:hover, .nav-item.active { background: #334155; color: #fff; }
        .nav-item i { width: 24px; }
        .section-title { font-size: 0.75rem; text-transform: uppercase; color: #64748b; margin: 1.5rem 0 0.5rem 0.5rem; font-weight: 600; }

        /* Main */
        .main { flex: 1; overflow-y: auto; padding: 2rem; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
        h1 { font-size: 1.8rem; font-weight: 600; }
        
        /* Utility */
        .alert { padding:1rem; margin-bottom:1rem; border-radius:0.5rem; }
        .alert-success { background: #166534; color: #86efac; }
        .alert-error { background: #7f1d1d; color: #fca5a5; }
        
        /* Stats, Cards, Forms */
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }
        .stat-card { background: var(--card); padding: 1.5rem; border-radius: 1rem; border: 1px solid var(--border); }
        .stat-label { color: var(--text-muted); font-size: 0.9rem; display: flex; justify-content: space-between; align-items: center; }
        .stat-value { font-size: 1.8rem; font-weight: 700; margin-top: 0.5rem; color: #fff; }
        .status-dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; }
        .status-online { background: #22c55e; box-shadow: 0 0 10px #22c55e; }
        .status-offline { background: #ef4444; }
        
        .btn { padding: 0.5rem 1rem; border-radius: 0.4rem; border: none; cursor: pointer; font-size: 0.9rem; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; color: white; }
        .btn-primary { background: var(--primary); }
        .btn-danger { background: #ef4444; }
        .btn-sm { padding: 0.3rem 0.6rem; font-size: 0.8rem; }
        .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
        .btn-ghost:hover { background: #334155; color: white; }
        
        /* Tables & Forms */
        .card-panel { background: var(--card); border-radius: 1rem; border: 1px solid var(--border); overflow: hidden; margin-bottom: 2rem; }
        .panel-header { padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: #182236; }
        .panel-title { font-size: 1.1rem; font-weight: 600; }
        .form-input, .form-select { width: 100%; padding: 0.6rem; background: #0f172a; border: 1px solid var(--border); color: white; border-radius: 0.4rem; }
        .form-group { margin-bottom: 1rem; }
        .form-label { display: block; margin-bottom: 0.5rem; color: var(--text-muted); font-size: 0.9rem; }
        
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 1rem 1.5rem; text-align: left; border-bottom: 1px solid var(--border); }
        th { color: var(--text-muted); font-weight: 500; font-size: 0.85rem; text-transform: uppercase; background: #182236; }
        tr:hover { background: #243046; }
        
        /* Modal Fix */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 100; align-items: center; justify-content: center; backdrop-filter: blur(2px); }
        .modal.active { display: flex; }
        .modal-content { background: var(--card); padding: 2rem; border-radius: 1rem; border: 1px solid var(--border); }

    </style>
</head>
<body>

    <nav class="sidebar">
        <div class="logo"><i class="fas fa-network-wired"></i> API Gateway V2</div>
        
        <div class="section-title">Menu</div>
        <a href="/dashboard" class="nav-item {{ 'active' if active_page == 'dashboard' else '' }}">
            <i class="fas fa-chart-line"></i> Dashboard
        </a>
        <a href="/endpoints" class="nav-item {{ 'active' if active_page == 'endpoints' else '' }}">
            <i class="fas fa-database"></i> Endpoints
        </a>
        
        <div class="section-title">Beheer</div>
        <a href="/users" class="nav-item {{ 'active' if active_page == 'users' else '' }}">
            <i class="fas fa-users"></i> Gebruikers
        </a>
        <a href="/migrate" class="nav-item {{ 'active' if active_page == 'migrate' else '' }}">
            <i class="fas fa-magic"></i> Migratie
        </a>
        
        <a href="/settings" class="nav-item {{ 'active' if active_page == 'settings' else '' }}" style="margin-top: auto;">
            <i class="fas fa-cogs"></i> Instellingen
        </a>
    </nav>

    <main class="main">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for c, m in messages %}
              <div class="alert alert-{{c}}">{{ m }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        {{ content | safe }}
    </main>

    <div id="addUserModal" class="modal">
        <div class="modal-content" style="max-width:400px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:1.5rem;">
                <h3>Nieuwe Gebruiker</h3>
                <span onclick="closeModal('addUserModal')" style="cursor:pointer; font-size:1.5rem; color:var(--text-muted)">&times;</span>
            </div>
            <form action="/users/add" method="POST">
                <div class="form-group">
                    <label class="form-label">Gebruikersnaam</label>
                    <input type="text" name="username" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Wachtwoord</label>
                    <input type="password" name="password" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Token Geldigheid</label>
                    <select name="validity" class="form-select">
                        <option value="24">24 Uur (Standaard)</option>
                        <option value="168">7 Dagen</option>
                        <option value="8760">1 Jaar</option>
                    </select>
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%">Aanmaken</button>
            </form>
        </div>
    </div>
    
    <div id="addEndpointModal" class="modal">
        <div class="modal-content" style="max-width:400px;">
            <h3>Nieuw Endpoint</h3><br>
            <form action="/manage/add" method="POST">
                <input type="text" name="app_name" class="form-input" placeholder="App Naam" style="margin-bottom:10px;" required>
                <input type="text" name="endpoint_name" class="form-input" placeholder="Endpoint Naam" style="margin-bottom:10px;" required>
                <button class="btn btn-primary" style="width:100%">Opslaan</button>
            </form>
            <br><button class="btn btn-ghost" style="width:100%" onclick="closeModal('addEndpointModal')">Annuleren</button>
        </div>
    </div>
    
    <div id="importModal" class="modal">
        <div class="modal-content" style="max-width:400px;">
            <h3>Importeer JSON</h3><br>
            <form id="importForm" action="" method="POST" enctype="multipart/form-data">
                <input type="file" name="file" class="form-input" style="margin-bottom:10px;" required>
                <button class="btn btn-primary" style="width:100%">Uploaden</button>
            </form>
            <br><button class="btn btn-ghost" style="width:100%" onclick="closeModal('importModal')">Annuleren</button>
        </div>
    </div>

    <script>
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
        function openImportModal(app, ep) {
            document.getElementById('importForm').action = `/manage/import/${app}/${ep}`;
            openModal('importModal');
        }
    </script>
</body>
</html>
"""

# De andere CONTENT variabelen zijn nu in de app.py geplakt.

DASHBOARD_CONTENT = """
<div class="header">
    <h1>Systeem Status</h1>
    <span class="badge badge-blue">Host: {{ db_host }}</span>
</div>
...
"""
# ... (de rest van de content strings is in de app.py hieronder)
