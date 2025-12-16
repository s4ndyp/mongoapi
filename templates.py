# templates.py

# ------------------------------------------------------------------------------
# 1. LOGIN PAGINA (Nieuwe donkere stijl)
# ------------------------------------------------------------------------------
LOGIN_CONTENT = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - API Gateway</title>
    <style>
        body {
            font-family: 'Inter', sans-serif;
            background-color: #0f172a;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .login-card {
            background-color: #1e293b;
            padding: 2.5rem;
            border-radius: 1rem;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            border: 1px solid #334155;
        }
        h2 { text-align: center; margin-bottom: 2rem; color: #fff; }
        .form-group { margin-bottom: 1.5rem; }
        label { display: block; margin-bottom: 0.5rem; font-size: 0.9rem; color: #94a3b8; }
        input {
            width: 100%;
            padding: 0.75rem;
            background-color: #0f172a;
            border: 1px solid #334155;
            color: #fff;
            border-radius: 0.5rem;
            box-sizing: border-box;
        }
        input:focus { outline: none; border-color: #2563eb; }
        button {
            width: 100%;
            padding: 0.75rem;
            background-color: #2563eb;
            color: white;
            border: none;
            border-radius: 0.5rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover { background-color: #1d4ed8; }
        .alert {
            padding: 0.75rem;
            margin-bottom: 1.5rem;
            border-radius: 0.5rem;
            font-size: 0.9rem;
            background-color: #fef2f2;
            color: #ef4444;
            border: 1px solid #fecaca;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>API Gateway</h2>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form method="POST">
            <div class="form-group">
                <label>Gebruikersnaam</label>
                <input type="text" name="username" required autofocus>
            </div>
            <div class="form-group">
                <label>Wachtwoord</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">Inloggen</button>
        </form>
    </div>
</body>
</html>
"""

# ------------------------------------------------------------------------------
# 2. DASHBOARD (De volledige applicatie UI)
# ------------------------------------------------------------------------------
# Dit bevat de Sidebar, Modals, en Javascript logic.
DASHBOARD_CONTENT = """
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
            --background-color: #0f172a; /* Dark theme base */
            --sidebar-bg: #1e293b;
            --sidebar-text: #94a3b8;
            --sidebar-active: #fff;
            --card-bg: #1e293b;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --border-color: #334155;
            --success: #22c55e;
            --danger: #ef4444;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: var(--background-color); color: var(--text-primary); display: flex; height: 100vh; overflow: hidden; }

        /* Sidebar */
        .sidebar { width: 280px; background: var(--sidebar-bg); border-right: 1px solid var(--border-color); display: flex; flex-direction: column; padding: 1.5rem; transition: all 0.3s ease; }
        .sidebar-header { margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border-color); }
        .logo { font-size: 1.25rem; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 0.75rem; }
        
        .nav-section { margin-bottom: 2rem; }
        .nav-title { text-transform: uppercase; font-size: 0.75rem; font-weight: 600; color: #64748b; margin-bottom: 0.75rem; letter-spacing: 0.05em; }
        .nav-item { display: flex; align-items: center; padding: 0.75rem 1rem; color: var(--sidebar-text); text-decoration: none; border-radius: 0.5rem; transition: all 0.2s; margin-bottom: 0.25rem; }
        .nav-item:hover, .nav-item.active { background: #334155; color: var(--sidebar-active); }
        .nav-item i { width: 20px; margin-right: 0.75rem; }

        /* Main Content */
        .main-content { flex: 1; overflow-y: auto; padding: 2rem; background: var(--background-color); }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
        
        .header-left h1 { font-size: 1.8rem; font-weight: 600; color: var(--text-primary); }
        .header-left p { color: var(--text-secondary); margin-top: 0.25rem; }
        .app-title-wrapper { display: flex; align-items: center; gap: 10px; }
        .edit-icon { color: var(--text-secondary); cursor: pointer; font-size: 0.9rem; transition: 0.2s; }
        .edit-icon:hover { color: var(--primary-color); }

        .btn { padding: 0.6rem 1.2rem; border-radius: 0.5rem; border: none; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 0.5rem; transition: all 0.2s; text-decoration: none; font-size: 0.9rem; }
        .btn-primary { background: var(--primary-color); color: white; }
        .btn-primary:hover { background: #1d4ed8; }
        .btn-danger { background: var(--danger); color: white; }
        .btn-sm { padding: 0.4rem 0.8rem; font-size: 0.8rem; }
        .btn-ghost { background: transparent; color: var(--text-secondary); border: 1px solid var(--border-color); }
        .btn-ghost:hover { background: #334155; color: var(--text-primary); }

        /* Grid & Cards */
        .grid-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem; }
        .card { background: var(--card-bg); border-radius: 1rem; padding: 1.5rem; border: 1px solid var(--border-color); transition: transform 0.2s; }
        .card:hover { transform: translateY(-2px); border-color: #475569; }
        
        .card-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 1rem; }
        .method-badge { background: #1e3a8a; color: #93c5fd; padding: 0.25rem 0.6rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 600; }
        .card-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; color: #f8fafc; }
        .card-path { font-family: 'Monaco', 'Consolas', monospace; font-size: 0.85rem; color: #cbd5e1; background: #0f172a; padding: 0.4rem 0.6rem; border-radius: 0.25rem; word-break: break-all; border: 1px solid var(--border-color); }
        
        .stat-row { display: flex; gap: 1.5rem; margin: 1rem 0; padding: 1rem 0; border-top: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color); }
        .stat-item { display: flex; flex-direction: column; }
        .stat-label { font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; }
        .stat-value { font-weight: 600; color: var(--text-primary); }

        .card-actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 1rem; }

        /* Forms & Modals */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; backdrop-filter: blur(2px); }
        .modal.active { display: flex; }
        .modal-content { background: var(--card-bg); padding: 2rem; border-radius: 1rem; width: 100%; max-width: 500px; border: 1px solid var(--border-color); color: var(--text-primary); }
        .modal-header { display: flex; justify-content: space-between; margin-bottom: 1.5rem; }
        .modal-title { font-size: 1.25rem; font-weight: 600; }
        .close-modal { cursor: pointer; font-size: 1.5rem; color: var(--text-secondary); }
        
        .form-group { margin-bottom: 1.25rem; }
        .form-label { display: block; margin-bottom: 0.5rem; font-weight: 500; font-size: 0.9rem; color: var(--text-secondary); }
        .form-input { width: 100%; padding: 0.75rem; background: #0f172a; border: 1px solid var(--border-color); border-radius: 0.5rem; font-family: inherit; color: white; transition: border-color 0.2s; }
        .form-input:focus { outline: none; border-color: var(--primary-color); }

        .flash-messages { margin-bottom: 1.5rem; }
        .alert { padding: 1rem; border-radius: 0.5rem; margin-bottom: 0.5rem; font-size: 0.9rem; }
        .alert-error { background: rgba(239, 68, 68, 0.1); color: #fca5a5; border: 1px solid #7f1d1d; }
        .alert-success { background: rgba(34, 197, 94, 0.1); color: #86efac; border: 1px solid #14532d; }
        
        .logout-btn { margin-top: auto; color: #ef4444 !important; }
        .logout-btn:hover { background: rgba(239, 68, 68, 0.1) !important; }
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
        
        <a href="/logout" class="nav-item logout-btn">
            <i class="fas fa-sign-out-alt"></i> Uitloggen
        </a>
    </aside>

    <main class="main-content">
        
        <div class="header">
            <div class="header-left">
                <div class="app-title-wrapper">
                    <h1>{% if selected_app %}{{ selected_app }}{% else %}Alle Endpoints{% endif %}</h1>
                    {% if selected_app %}
                    <i class="fas fa-pencil-alt edit-icon" onclick="openRenameAppModal('{{ selected_app }}')" title="Applicatie hernoemen"></i>
                    {% endif %}
                </div>
                <p>Beheer API connecties en data</p>
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
                        <span class="stat-label">Records</span>
                        <span class="stat-value">{{ ep.doc_count }}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Datum</span>
                        <span class="stat-value">{{ ep.created_at.strftime('%d-%m-%Y') if ep.created_at else '-' }}</span>
                    </div>
                </div>

                <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 1rem;">
                    {{ ep.description }}
                </p>

                <div class="card-actions">
                    <a href="/manage/export/{{ ep.app_name }}/{{ ep.endpoint_name }}" class="btn btn-ghost btn-sm" title="Backup downloaden">
                        <i class="fas fa-download"></i>
                    </a>
                    <button class="btn btn-ghost btn-sm" onclick="openImportModal('{{ ep.app_name }}', '{{ ep.endpoint_name }}')" title="Data importeren">
                        <i class="fas fa-upload"></i>
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="openRenameEndpointModal('{{ ep.app_name }}', '{{ ep.endpoint_name }}')" title="Wijzigen">
                        <i class="fas fa-edit"></i>
                    </button>
                    <form action="/manage/delete" method="POST" onsubmit="return confirm('LET OP: Dit verwijdert het endpoint én alle data definitief!');" style="display:inline;">
                        <input type="hidden" name="app_name" value="{{ ep.app_name }}">
                        <input type="hidden" name="endpoint_name" value="{{ ep.endpoint_name }}">
                        <button type="submit" class="btn btn-ghost btn-sm" style="color: var(--danger);" title="Verwijderen">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </form>
                </div>
            </div>
            {% else %}
            <div style="grid-column: 1/-1; text-align: center; padding: 4rem; color: var(--text-secondary);">
                <i class="fas fa-cubes" style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.2;"></i>
                <p>Geen endpoints gevonden.</p>
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
                    <label class="form-label">Applicatie (Map)</label>
                    <input type="text" name="app_name" class="form-input" placeholder="bv. KlantenApp" value="{{ selected_app if selected_app else '' }}" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Endpoint Naam</label>
                    <input type="text" name="endpoint_name" class="form-input" placeholder="bv. data" value="data" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Beschrijving</label>
                    <input type="text" name="description" class="form-input" placeholder="Optioneel">
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
                <i class="fas fa-exclamation-triangle"></i> Let op: Dit verandert de URL paden en hernoemt de database collecties.
            </p>
            <form action="/manage/rename_app" method="POST">
                <input type="hidden" name="old_app_name" id="rename_old_app_name">
                <div class="form-group">
                    <label class="form-label">Nieuwe Naam</label>
                    <input type="text" name="new_app_name" class="form-input" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">Opslaan</button>
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
                <h3 class="modal-title">Importeer Data</h3>
                <span class="close-modal" onclick="closeModal('importModal')">&times;</span>
            </div>
            <form action="" method="POST" enctype="multipart/form-data" id="importForm">
                <div class="form-group">
                    <label class="form-label">JSON Bestand</label>
                    <input type="file" name="file" class="form-input" accept=".json" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">Uploaden</button>
            </form>
        </div>
    </div>

    <script>
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
        window.onclick = function(e) { if(e.target.classList.contains('modal')) e.target.classList.remove('active'); }

        function openRenameAppModal(name) {
            document.getElementById('rename_old_app_name').value = name;
            openModal('renameAppModal');
        }
        function openRenameEndpointModal(app, ep) {
            document.getElementById('rename_ep_app_name').value = app;
            document.getElementById('rename_ep_old_name').value = ep;
            openModal('renameEndpointModal');
        }
        function openImportModal(app, ep) {
            document.getElementById('importForm').action = `/manage/import/${app}/${ep}`;
            openModal('importModal');
        }
    </script>
</body>
</html>
"""
