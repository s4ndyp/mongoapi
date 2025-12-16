# templates.py

# ------------------------------------------------------------------------------
# 1. SETUP PAGINA (Voor DB Connectie)
# ------------------------------------------------------------------------------
SETUP_CONTENT = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Setup - API Gateway</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body { background: #0f172a; color: #f1f5f9; font-family: 'Inter', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; width: 100%; max-width: 450px; border: 1px solid #334155; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); }
        h2 { margin-top: 0; color: #fff; text-align: center; }
        p { color: #94a3b8; text-align: center; margin-bottom: 2rem; font-size: 0.9rem; }
        label { display: block; margin-bottom: 0.5rem; font-size: 0.9rem; color: #cbd5e1; }
        input { width: 100%; padding: 0.75rem; background: #0f172a; border: 1px solid #334155; color: white; border-radius: 0.5rem; box-sizing: border-box; margin-bottom: 1.5rem; }
        input:focus { outline: none; border-color: #3b82f6; }
        button { width: 100%; padding: 0.75rem; background: #2563eb; color: white; border: none; border-radius: 0.5rem; font-weight: 600; cursor: pointer; }
        button:hover { background: #1d4ed8; }
        .alert { background: #7f1d1d; color: #fca5a5; padding: 0.75rem; border-radius: 0.5rem; margin-bottom: 1.5rem; font-size: 0.9rem; text-align: center; border: 1px solid #ef4444; }
    </style>
</head>
<body>
    <div class="card">
        <h2><i class="fas fa-plug"></i> Database Setup</h2>
        <p>Er kon geen verbinding worden gemaakt met MongoDB.<br>Voer de verbindingsgegevens in.</p>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form method="POST">
            <label>MongoDB Host (bv. localhost of IP)</label>
            <input type="text" name="host" value="localhost" required>
            
            <label>Poort (Standaard: 27017)</label>
            <input type="number" name="port" value="27017" required>
            
            <button type="submit">Verbinden & Opslaan</button>
        </form>
    </div>
</body>
</html>
"""

# ------------------------------------------------------------------------------
# 2. LOGIN PAGINA
# ------------------------------------------------------------------------------
LOGIN_CONTENT = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Login - API Gateway</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body { background: #0f172a; color: #e2e8f0; font-family: 'Inter', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; width: 100%; max-width: 400px; border: 1px solid #334155; }
        h2 { text-align: center; margin-bottom: 2rem; color: #fff; }
        input { width: 100%; padding: 0.75rem; background: #0f172a; border: 1px solid #334155; color: #fff; border-radius: 0.5rem; margin-bottom: 1.25rem; box-sizing: border-box; }
        button { width: 100%; padding: 0.75rem; background: #2563eb; color: white; border: none; border-radius: 0.5rem; font-weight: 600; cursor: pointer; }
        .alert { padding: 0.75rem; margin-bottom: 1.5rem; border-radius: 0.5rem; background: #450a0a; color: #fca5a5; border: 1px solid #b91c1c; text-align: center; }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>API Gateway V2</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}{% for c, m in messages %}<div class="alert">{{ m }}</div>{% endfor %}{% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="username" placeholder="Gebruikersnaam" required autofocus>
            <input type="password" name="password" placeholder="Wachtwoord" required>
            <button type="submit">Inloggen</button>
        </form>
    </div>
</body>
</html>
"""

# ------------------------------------------------------------------------------
# 3. DASHBOARD (Full App)
# ------------------------------------------------------------------------------
DASHBOARD_CONTENT = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>API Dashboard</title>
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
        
        /* Dashboard Stats Cards */
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }
        .stat-card { background: var(--card); padding: 1.5rem; border-radius: 1rem; border: 1px solid var(--border); }
        .stat-label { color: var(--text-muted); font-size: 0.9rem; display: flex; justify-content: space-between; align-items: center; }
        .stat-value { font-size: 1.8rem; font-weight: 700; margin-top: 0.5rem; color: #fff; }
        .status-dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; }
        .status-online { background: #22c55e; box-shadow: 0 0 10px #22c55e; }
        .status-offline { background: #ef4444; }

        /* Tables & Lists */
        .card-panel { background: var(--card); border-radius: 1rem; border: 1px solid var(--border); overflow: hidden; margin-bottom: 2rem; }
        .panel-header { padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: #1e293b; }
        .panel-title { font-size: 1.1rem; font-weight: 600; }
        
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 1rem 1.5rem; text-align: left; border-bottom: 1px solid var(--border); }
        th { color: var(--text-muted); font-weight: 500; font-size: 0.85rem; text-transform: uppercase; background: #182236; }
        tr:hover { background: #243046; }
        td { font-size: 0.95rem; }
        
        /* Buttons */
        .btn { padding: 0.5rem 1rem; border-radius: 0.4rem; border: none; cursor: pointer; font-size: 0.9rem; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; color: white; }
        .btn-primary { background: var(--primary); }
        .btn-danger { background: #ef4444; }
        .btn-sm { padding: 0.3rem 0.6rem; font-size: 0.8rem; }
        .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
        .btn-ghost:hover { background: #334155; color: white; }

        /* Modal */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 100; align-items: center; justify-content: center; backdrop-filter: blur(2px); }
        .modal.active { display: flex; }
        .modal-content { background: var(--card); padding: 2rem; width: 100%; max-width: 500px; border-radius: 1rem; border: 1px solid var(--border); }
        
        .form-group { margin-bottom: 1rem; }
        .form-label { display: block; margin-bottom: 0.5rem; color: var(--text-muted); font-size: 0.9rem; }
        .form-input, .form-select { width: 100%; padding: 0.6rem; background: #0f172a; border: 1px solid var(--border); color: white; border-radius: 0.4rem; }
        
        .badge { padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }
        .badge-blue { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
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
        
        <a href="/logout" class="nav-item" style="margin-top: auto; color: #ef4444;">
            <i class="fas fa-sign-out-alt"></i> Uitloggen
        </a>
    </nav>

    <main class="main">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for c, m in messages %}
              <div style="padding:1rem; margin-bottom:1rem; border-radius:0.5rem; background: {{ '#166534' if c=='success' else '#7f1d1d' }}; color:white;">
                  {{ m }}
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        {% if active_page == 'dashboard' %}
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

        {% elif active_page == 'users' %}
        <div class="header">
            <h1>Gebruikersbeheer</h1>
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
                            <small class="text-muted">Systeem Admin</small>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div id="addUserModal" class="modal">
            <div class="modal-content">
                <div style="display:flex; justify-content:space-between; margin-bottom:1.5rem;">
                    <h3>Nieuwe Gebruiker</h3>
                    <span onclick="closeModal('addUserModal')" style="cursor:pointer; font-size:1.5rem;">&times;</span>
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

        {% elif active_page == 'endpoints' %}
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
        
        <div id="addEndpointModal" class="modal">
            <div class="modal-content">
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
            <div class="modal-content">
                <h3>Importeer JSON</h3><br>
                <form id="importForm" action="" method="POST" enctype="multipart/form-data">
                    <input type="file" name="file" class="form-input" style="margin-bottom:10px;" required>
                    <button class="btn btn-primary" style="width:100%">Uploaden</button>
                </form>
                <br><button class="btn btn-ghost" style="width:100%" onclick="closeModal('importModal')">Annuleren</button>
            </div>
        </div>

        {% endif %}
    </main>

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
