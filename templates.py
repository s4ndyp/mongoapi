# templates.py

# ------------------------------------------------------------------------------
# 1. BASE LAYOUT & Setup Content (Gewijzigd)
# ------------------------------------------------------------------------------
# We houden het simpel voor de dashboard view
BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>{{ title }} - API Gateway V2</title>
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

    </style>
</head>
<body>

    <nav class="sidebar">
        <div class="logo"><i class="fas fa-network-wired"></i> API Gateway V2</div>
        
        <div class="section-title">Menu</div>
        <a href="/" class="nav-item {{ 'active' if active_page == 'dashboard' else '' }}">
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

        {{ content }}
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

# ------------------------------------------------------------------------------
# 2. DASHBOARD PAGINA'S
# ------------------------------------------------------------------------------
DASHBOARD_CONTENT = """
<div class="header">
    <h1>Systeem Status</h1>
    <span class="badge badge-blue">Host: {{ db_host }}</span>
</div>

<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-label">Database Status <div class="status-dot {{ 'status-online' if db_status else 'status-offline' }}"></div></div>
        <div class="stat-value">{{ 'Verbonden' if db_status else 'Fout' }}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Totale Opslag <i class="fas fa-hdd"></i></div>
        <div class="stat-value">{{ db_storage }}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Mislukte Logins (24u) <i class="fas fa-shield-alt"></i></div>
        <div class="stat-value" style="color: #ef4444;">{{ failed_logins }}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Totaal Endpoints <i class="fas fa-layer-group"></i></div>
        <div class="stat-value">{{ total_endpoints }}</div>
    </div>
</div>

<div class="card-panel">
    <div class="panel-header">
        <span class="panel-title">Activiteit (Afgelopen 7 dagen)</span>
    </div>
    <div style="padding: 1rem; height: 300px;">
        <canvas id="activityChart"></canvas>
    </div>
</div>

<script>
    const ctx = document.getElementById('activityChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: {{ chart_labels | safe }},
            datasets: [{
                label: 'Requests',
                data: {{ chart_data | safe }},
                backgroundColor: '#3b82f6',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: '#334155' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            },
            plugins: { legend: { display: false } }
        }
    });
</script>
"""

ENDPOINTS_CONTENT = """
<div class="header">
    <h1>Endpoints Data</h1>
    <button class="btn btn-primary" onclick="openModal('addEndpointModal')"><i class="fas fa-plus"></i> Nieuw</button>
</div>

<div class="stats-grid">
    {% for ep in endpoints %}
    <div class="stat-card">
        <div class="stat-label" style="margin-bottom: 0.5rem;">
            <span>{{ ep.app_name }}</span>
            <i class="fas fa-database" style="color: var(--primary);"></i>
        </div>
        <h3 style="color: white; margin-bottom: 0.25rem;">/{{ ep.endpoint_name }}</h3>
        <small style="color: var(--text-muted);">{{ ep.doc_count }} documenten</small>
        
        <div style="display: flex; gap: 5px; margin-top: 1rem;">
            <a href="/manage/export/{{ ep.app_name }}/{{ ep.endpoint_name }}" class="btn btn-sm btn-ghost" title="Backup"><i class="fas fa-download"></i></a>
            
            <button class="btn btn-sm btn-ghost" onclick="openImportModal('{{ ep.app_name }}', '{{ ep.endpoint_name }}')" title="Import"><i class="fas fa-upload"></i></button>
            
            <form action="/manage/empty" method="POST" onsubmit="return confirm('Weet je zeker dat je dit endpoint LEEG wilt maken? Alle data verdwijnt.');" style="display:inline;">
                <input type="hidden" name="app_name" value="{{ ep.app_name }}">
                <input type="hidden" name="endpoint_name" value="{{ ep.endpoint_name }}">
                <button class="btn btn-sm btn-ghost" style="color:orange;" title="Leegmaken (Truncate)"><i class="fas fa-eraser"></i></button>
            </form>

            <form action="/manage/delete" method="POST" onsubmit="return confirm('Verwijder endpoint definitief?');" style="display:inline;">
                <input type="hidden" name="app_name" value="{{ ep.app_name }}">
                <input type="hidden" name="endpoint_name" value="{{ ep.endpoint_name }}">
                <button class="btn btn-sm btn-ghost" style="color: #ef4444;" title="Verwijderen"><i class="fas fa-trash"></i></button>
            </form>
        </div>
    </div>
    {% endfor %}
</div>
"""

USERS_CONTENT = """
<div class="header">
    <h1>Gebruikersbeheer (Client API Toegang)</h1>
    <button class="btn btn-primary" onclick="openModal('addUserModal')"><i class="fas fa-plus"></i> Nieuwe Gebruiker</button>
</div>

<div class="card-panel">
    <table>
        <thead>
            <tr>
                <th>Gebruikersnaam</th>
                <th>Token Geldigheid</th>
                <th>Aangemaakt op</th>
                <th>Acties</th>
            </tr>
        </thead>
        <tbody>
            {% for user in users %}
            <tr>
                <td style="font-weight: 500; color: white;"><i class="fas fa-user-circle"></i> {{ user.username }}</td>
                <td>
                    <span class="badge badge-blue">
                        {{ user.token_validity_hours }} uur 
                        ({% if user.token_validity_hours == 24 %}1 dag{% elif user.token_validity_hours == 168 %}7 dagen{% elif user.token_validity_hours == 8760 %}1 jaar{% else %}Custom{% endif %})
                    </span>
                </td>
                <td>{{ user.created_at.strftime('%d-%m-%Y') if user.created_at else '-' }}</td>
                <td>
                    {% if user.username != 'admin' %}
                    <form action="/users/delete" method="POST" onsubmit="return confirm('Gebruiker verwijderen?');">
                        <input type="hidden" name="user_id" value="{{ user._id }}">
                        <button class="btn btn-sm btn-danger"><i class="fas fa-trash"></i></button>
                    </form>
                    {% else %}
                    <small class="text-muted">Dashboard User (niet verwijderbaar)</small>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

MIGRATION_CONTENT = """
<div class="header">
    <h1><i class="fas fa-magic"></i> Database Migratie</h1>
</div>
<p style="color: var(--text-muted); margin-bottom: 2rem;">
    Hieronder staan database collecties die nog niet gekoppeld zijn aan de nieuwe `/api/{app}/{endpoint}` structuur. 
    Geef ze een Applicatie- en Endpointnaam om ze te importeren.
</p>

{% if orphans %}
<div class="card-panel">
    <div class="panel-header"><span class="panel-title">Ongekoppelde Collecties</span></div>
    <div style="padding: 1rem;">
        {% for col in orphans %}
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding:10px 0;">
            <div>
                <span style="font-family: monospace; font-size: 1.1rem; color: #cbd5e1;">{{ col }}</span>
                <div style="font-size: 0.8rem; color: var(--text-muted);">{{ counts[col] }} documenten</div>
            </div>
            <form style="display:flex; gap:10px;" action="/migrate/do" method="POST">
                <input type="hidden" name="old_name" value="{{ col }}">
                <input type="text" name="new_app" placeholder="App Naam" class="form-input" style="width:120px;" required>
                <input type="text" name="new_ep" placeholder="Endpoint" class="form-input" style="width:120px;" required>
                <button type="submit" class="btn btn-sm btn-primary">Migreer</button>
            </form>
        </div>
        {% endfor %}
    </div>
</div>
{% else %}
<div style="text-align: center; color: var(--text-muted); padding: 4rem; background: var(--card); border-radius: 1rem; border: 1px solid var(--border);">
    <i class="fas fa-check-circle" style="font-size: 2rem; color: #22c55e;"></i><br><br>
    Geen ongekoppelde collecties gevonden. Alles is up-to-date!
</div>
{% endif %}
"""

SETTINGS_CONTENT = """
<div class="header">
    <h1><i class="fas fa-cogs"></i> Instellingen</h1>
</div>

<div class="stats-grid">
    <div class="stat-card" style="grid-column: span 2;">
        <div class="stat-label" style="margin-bottom: 1rem;"><span>Database Connectie</span></div>
        
        <form method="POST">
            <div class="form-group">
                <label class="form-label">Host / IP Adres</label>
                <input type="text" name="host" class="form-input" value="{{ config.get('mongo_host', 'localhost') }}" required>
            </div>
            <div class="form-group">
                <label class="form-label">Poort</label>
                <input type="number" name="port" class="form-input" value="{{ config.get('mongo_port', 27017) }}" required>
            </div>
            <div class="form-group">
                <label class="form-label">Database User (Optioneel)</label>
                <input type="text" name="mongo_user" class="form-input" value="{{ config.get('mongo_user', '') }}" placeholder="Leeglaten indien geen auth">
            </div>
             <div class="form-group">
                <label class="form-label">Database Wachtwoord (Optioneel)</label>
                <input type="password" name="mongo_pass" class="form-input" value="" placeholder="Niet getoond om veiligheidsredenen">
                <input type="hidden" name="current_mongo_pass_hash" value="{{ config.get('mongo_pass_hash', '') }}">
            </div>

            <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Opslaan & Testen</button>
            <small style="color: var(--text-muted); margin-left: 1rem;">Huidige status: <span style="color:{{ 'lime' if db_status else 'red' }}; font-weight:bold;">{{ 'Verbonden' if db_status else 'Niet Verbonden' }}</span></small>
        </form>
    </div>
</div>
"""
