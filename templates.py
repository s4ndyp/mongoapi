# templates.py

LOGIN_CONTENT = """
    <div class="row justify-content-center pt-5">
        <div class="col-md-6 col-lg-4">
            <div class="card p-4 shadow-lg">
                <h3 class="card-title text-center mb-4 text-white"><i class="bi bi-lock-fill"></i> Dashboard Login</h3>
                {% with messages = get_flashed_messages(with_categories=true) %}
                  {% if messages %}
                    {% for category, message in messages %}
                      <div class="alert alert-{{ category }}">{{ message | safe }}</div>
                    {% endfor %}
                  {% endif %}
                {% endwith %}
                <form method="POST" action="{{ url_for('dashboard_login') }}">
                    <div class="mb-3">
                        <label for="username" class="form-label text-muted">Gebruikersnaam</label>
                        <input type="text" name="username" id="username" class="form-control bg-dark text-white" required autofocus>
                    </div>
                    <div class="mb-4">
                        <label for="password" class="form-label text-muted">Wachtwoord</label>
                        <input type="password" name="password" id="password" class="form-control bg-dark text-white" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">Log In</button>
                </form>
            </div>
        </div>
    </div>
"""

BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="nl" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Gateway V2</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #121212; color: #e0e0e0; }
        .card { background-color: #1e1e1e; border: 1px solid #333; margin-bottom: 20px; }
        .sidebar { min-height: 100vh; background-color: #191919; border-right: 1px solid #333; }
        .nav-link { color: #aaa; }
        .nav-link:hover, .nav-link.active { color: #fff; background-color: #333; border-radius: 5px; }
        .status-dot { height: 12px; width: 12px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .dot-green { background-color: #28a745; box-shadow: 0 0 5px #28a745; }
        .dot-red { background-color: #dc3545; box-shadow: 0 0 5px #dc3545; }
        .log-timestamp { font-family: monospace; color: #88c0d0; }
        .fixed-top { position: fixed; top: 0; }
        .jwt-input-fix {
             width: 100%;
             word-wrap: break-word; 
             min-width: 0; 
             height: auto; 
        }
        .tag-pill {
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 10px;
            margin-right: 4px;
            text-decoration: none;
            display: inline-block;
        }
        .tag-pill:hover { opacity: 0.8; color: #fff !important; }
        .tag-pill.active { border: 2px solid #0d6efd; background-color: transparent !important; color: #0d6efd !important; }
        
        /* AANGEPAST: 20 Dynamische kleuren voor tags op basis van hash */
        .tag-color-0 { background-color: #e67e22; color: #fff; } /* Oranje */
        .tag-color-1 { background-color: #27ae60; color: #fff; } /* Groen */
        .tag-color-2 { background-color: #9b59b6; color: #fff; } /* Paars */
        .tag-color-3 { background-color: #3498db; color: #fff; } /* Blauw */
        .tag-color-4 { background-color: #e74c3c; color: #fff; } /* Rood */
        .tag-color-5 { background-color: #1abc9c; color: #fff; } /* Turqouise */
        .tag-color-6 { background-color: #f1c40f; color: #000; } /* Geel */
        .tag-color-7 { background-color: #95a5a6; color: #000; } /* Lichtgrijs */
        .tag-color-8 { background-color: #d35400; color: #fff; } /* Donker Oranje */
        .tag-color-9 { background-color: #2ecc71; color: #fff; } /* Emerald Groen */
        .tag-color-10 { background-color: #8e44ad; color: #fff; } /* Donker Paars */
        .tag-color-11 { background-color: #2980b9; color: #fff; } /* Donker Blauw */
        .tag-color-12 { background-color: #c0392b; color: #fff; } /* Donker Rood */
        .tag-color-13 { background-color: #16a085; color: #fff; } /* Donker Turqouise */
        .tag-color-14 { background-color: #f39c12; color: #000; } /* Donker Geel */
        .tag-color-15 { background-color: #7f8c8d; color: #fff; } /* Grijs */
        .tag-color-16 { background-color: #bdc3c7; color: #000; } /* Heel Licht Grijs */
        .tag-color-17 { background-color: #34495e; color: #fff; } /* Midnight Blue */
        .tag-color-18 { background-color: #00b894; color: #fff; } /* Medium Turqouise */
        .tag-color-19 { background-color: #fd79a8; color: #000; } /* Roze */
        
        {% if page == 'login' %}
        .container-fluid { height: 100vh; display: flex; align-items: center; justify-content: center; }
        {% endif %}
    </style>
</head>
<body>
    <div id="dashboard-notification" class="alert alert-success d-none fixed-top mt-3 mx-auto shadow-lg" 
        style="width: 300px; z-index: 1050; text-align: center;"></div>

    <div class="container-fluid">
        <div class="row w-100">
            {% if page != 'login' %}
            <nav class="col-md-3 col-lg-2 d-md-block sidebar collapse p-3">
                <h4 class="mb-4 text-white"><i class="bi bi-hdd-network"></i> Gateway</h4>
                <ul class="nav flex-column mb-4">
                    <li class="nav-item"><a class="nav-link {{ 'active' if page == 'dashboard' else '' }}" href="/"><i class="bi bi-speedometer2"></i> Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link {{ 'active' if page == 'endpoints' else '' }}" href="/endpoints"><i class="bi bi-diagram-3"></i> Endpoints</a></li>
                    <li class="nav-item"><a class="nav-link {{ 'active' if page == 'settings' else '' }}" href="/settings"><i class="bi bi-gear"></i> Instellingen</a></li>
                </ul>

                {% if all_tags %}
                <h6 class="sidebar-heading d-flex justify-content-between align-items-center px-3 mt-4 mb-2 text-muted text-uppercase">
                  <span>Filter op Tag</span>
                </h6>
                <div class="px-3">
                    <a href="/endpoints" class="tag-pill mb-2 d-inline-block {{ 'active' if not request.args.get('tag') else get_tag_color_class('Alle') }}">Alle</a>
                    {% for tag in all_tags %}
                        <a href="{{ url_for('endpoints_page', tag=tag) }}" 
                           class="tag-pill mb-2 d-inline-block {{ 'active' if request.args.get('tag') == tag else get_tag_color_class(tag) }}">
                           {{ tag }}
                        </a>
                    {% endfor %}
                </div>
                {% endif %}

                <div class="mt-auto pt-4 border-top border-secondary small text-muted">
                    Ingelogd als: <strong class="text-white">{{ session.get('username', 'Gast') }}</strong>
                    <div class="mt-2">
                        <a href="{{ url_for('dashboard_logout') }}" class="btn btn-sm btn-outline-danger w-100"><i class="bi bi-box-arrow-right"></i> Uitloggen</a>
                    </div>
                    <div class="mt-4">Versie 2.7 (Split + Clear Data)</div>
                </div>
            </nav>
            {% endif %}
            
            <main class="{{ 'col-12' if page == 'login' else 'col-md-9 ms-sm-auto col-lg-10' }} px-md-4 py-4">
                {% if page != 'login' %}
                {% with messages = get_flashed_messages(with_categories=true) %}
                  {% if messages %}
                    {% for category, message in messages %}
                      <div class="alert alert-{{ category }} alert-dismissible fade show">{{ message | safe }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
                    {% endfor %}
                  {% endif %}
                {% endwith %}
                {% endif %}
                {{ page_content | safe }}
            </main>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        function showNotification(message, type = 'success') {
            const notif = document.getElementById('dashboard-notification');
            if (!notif) return;
            notif.className = `alert alert-${type} fixed-top mt-3 mx-auto shadow-lg`;
            notif.style.display = 'block';
            notif.innerHTML = message;
            setTimeout(() => { notif.style.display = 'none'; }, 3000);
        }

        function copyKey(elementId) {
            const inputElement = document.getElementById(elementId);
            if (!inputElement) return;
            inputElement.select();
            inputElement.setSelectionRange(0, 99999); 
            try {
                const successful = document.execCommand('copy');
                if (successful) showNotification('Gekopieerd!', 'success');
                else showNotification('Kopiëren mislukt.', 'danger');
            } catch (err) { showNotification('Kopiëren mislukt.', 'danger'); }
        }
        
        document.addEventListener("DOMContentLoaded", function() {
            document.querySelectorAll('.utc-timestamp').forEach(element => {
                const utcTime = element.dataset.utc;
                if (utcTime) {
                    const date = new Date(utcTime + 'Z'); 
                    if (!isNaN(date)) {
                        element.textContent = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
                    }
                }
            });
            const jwtCopyButton = document.getElementById('jwt-copy-button');
            if (jwtCopyButton) {
                jwtCopyButton.addEventListener('click', () => { copyKey('jwt-token-input'); });
            }
        });
    </script>
    {% if page == 'dashboard' %}
    <script>
        const chartData = JSON.parse(document.getElementById('chart-data').textContent);
        const ctx = document.getElementById('activityChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: 'Requests',
                    data: chartData.counts,
                    backgroundColor: 'rgba(13, 110, 253, 0.6)',
                    borderColor: '#0d6efd', borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                scales: { y: { beginAtZero: true, grid: { color: '#333' } }, x: { grid: { color: '#333' } } }
            }
        });
    </script>
    {% endif %}
</body>
</html>
"""

DASHBOARD_CONTENT = """
    <h2 class="mb-4">Systeem Overzicht</h2>
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card p-3">
                <h5 class="text-muted">Status</h5>
                <div class="d-flex align-items-center mt-2">
                    {% if db_connected %}
                        <span class="status-dot dot-green"></span> <h4 class="m-0">Online</h4>
                    {% else %}
                        <span class="status-dot dot-red"></span> <h4 class="m-0">Offline</h4>
                    {% endif %}
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3">
                <h5 class="text-muted">Requests (24u)</h5>
                <h3 class="mt-2">{{ stats_count }}</h3>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3">
                <h5 class="text-muted">Actieve Clients</h5>
                <h3 class="mt-2">{{ client_count }}</h3>
            </div>
        </div>
         <div class="col-md-3">
            <div class="card p-3 border-info">
                <h5 class="text-info">Totale Opslag</h5>
                <h3 class="mt-2">{{ total_storage }}</h3>
            </div>
        </div>
    </div>
    
    <div class="row mb-4">
        <div class="col-12">
            <div class="card p-3 border-warning">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="text-warning m-0"><i class="bi bi-person-fill-lock"></i> Mislukte Login Pogingen</h5>
                    <div class="dropdown">
                        <button class="btn btn-sm btn-warning dropdown-toggle" type="button" data-bs-toggle="dropdown">
                            {{ login_range_label }}
                        </button>
                        <ul class="dropdown-menu dropdown-menu-dark">
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range=time_range, login_range='24h') }}">Laatste 24 Uur</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range=time_range, login_range='7d') }}">Laatste 7 Dagen</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range=time_range, login_range='30d') }}">Laatste 30 Dagen</a></li>
                        </ul>
                    </div>
                </div>
                
                <ul class="list-group list-group-flush">
                    {% for client, count in failed_logins.items() %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between">
                        <span class="text-muted font-monospace">{{ client }}</span>
                        <span class="badge bg-danger">{{ count }}</span>
                    </li>
                    {% else %}
                    <li class="list-group-item bg-transparent text-muted">Geen mislukte login pogingen in deze periode.</li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>

    <div class="row">
        <div class="col-md-8">
            <div class="card p-3">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="m-0">Activiteit</h5>
                    <div class="dropdown">
                        <button class="btn btn-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
                            {{ current_range_label }}
                        </button>
                        <ul class="dropdown-menu dropdown-menu-dark">
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='6h', login_range=login_range) }}">Laatste 6 Uur</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='24h', login_range=login_range) }}">Laatste 24 Uur</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='7d', login_range=login_range) }}">Laatste Week</a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='30d', login_range=login_range) }}">Laatste Maand</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('dashboard', range='365d', login_range=login_range) }}">Laatste Jaar</a></li>
                        </ul>
                    </div>
                </div>
                <script id="chart-data" type="application/json">{{ chart_data | tojson | safe }}</script>
                <canvas id="activityChart" height="100"></canvas>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card p-3">
                <h5 class="card-title">Top Clients (24u)</h5>
                <ul class="list-group list-group-flush mt-3">
                    {% for client in clients %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between">
                        <a href="{{ url_for('client_detail', source_app=client) }}" class="text-info text-decoration-none">{{ client }}</a>
                        <span class="badge bg-primary">Actief</span>
                    </li>
                    {% else %}
                    <li class="list-group-item bg-transparent text-muted">Geen verkeer</li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>
"""

ENDPOINTS_CONTENT = """
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h2>Endpoints Beheer</h2>
            {% if active_filter %}
                <span class="tag-pill {{ get_tag_color_class(active_filter) }} active">Gefilterd op: {{ active_filter }}</span>
                <a href="/endpoints" class="btn btn-sm btn-outline-secondary ms-2">Reset</a>
            {% endif %}
        </div>
        <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addEndpointModal">
            <i class="bi bi-plus-lg"></i> Nieuw Endpoint
        </button>
    </div>

    <div class="row">
        {% for ep in endpoints %}
        <div class="col-md-6 col-xl-4">
            <div class="card h-100 {{ 'border-info' if ep.system else '' }}">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="m-0 font-monospace {{ 'text-info' if ep.system else 'text-white' }}">
                        /api/{{ ep.name }} 
                        {% if ep.system %}<i class="bi bi-shield-lock-fill small ms-1" title="Systeem Endpoint"></i>{% endif %}
                    </h5>
                    
                    <div class="d-flex gap-1">
                        <form method="POST" action="/endpoints/clear_data" onsubmit="return confirm('WEET U HET ZEKER? Dit verwijdert ALLE {{ ep.stats.count }} records in {{ ep.name }}. Dit kan niet ongedaan worden gemaakt.');">
                            <input type="hidden" name="name" value="{{ ep.name }}">
                            <button type="submit" class="btn btn-sm btn-outline-warning" title="Maak endpoint leeg (verwijder data)">
                                <i class="bi bi-eraser"></i>
                            </button>
                        </form>

                        {% if not ep.system %}
                        <button class="btn btn-sm btn-outline-secondary" 
                                onclick="openEditModal('{{ ep.name }}', '{{ ep.description | replace("'", "") | replace('"', "") }}', '{{ ep.tags | join(',') }}')" title="Bewerken">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <form method="POST" action="/endpoints/delete" onsubmit="return confirm('LET OP: Dit verwijdert het endpoint {{ ep.name }} EN alle data. Doorgaan?');">
                            <input type="hidden" name="name" value="{{ ep.name }}">
                            <button type="submit" class="btn btn-sm btn-outline-danger" title="Verwijder Endpoint"><i class="bi bi-trash"></i></button>
                        </form>
                        {% endif %}
                    </div>
                </div>
                <div class="card-body">
                    <p class="text-muted small">{{ ep.description }}</p>
                    <div class="mb-3">
                        {% for tag in ep.tags %}
                            <span class="tag-pill {{ get_tag_color_class(tag) }}">{{ tag }}</span>
                        {% endfor %}
                    </div>
                    <div class="row text-center mt-3">
                        <div class="col-6 border-end border-secondary">
                            <small class="text-muted">Records</small>
                            <div class="fs-5">{{ ep.stats.count }}</div>
                        </div>
                        <div class="col-6">
                            <small class="text-muted">Opslag</small>
                            <div class="fs-5 text-warning">{{ ep.stats.size }}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        {% else %}
        <div class="col-12 text-center text-muted py-5">
            <h4>Geen endpoints gevonden.</h4>
        </div>
        {% endfor %}
    </div>

    <div class="modal fade" id="addEndpointModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content bg-dark text-white border-secondary">
                <div class="modal-header border-secondary">
                    <h5 class="modal-title">Endpoint Toevoegen</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <form method="POST" action="/endpoints">
                    <div class="modal-body">
                        <div class="mb-3">
                            <label class="form-label">Naam (URL pad)</label>
                            <div class="input-group">
                                <span class="input-group-text bg-secondary text-white">/api/</span>
                                <input type="text" name="name" class="form-control bg-black text-white" required pattern="[a-zA-Z0-9_]+" placeholder="products">
                            </div>
                            <div class="form-text text-muted">Gereserveerd: 'data', 'items', 'projects'</div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Omschrijving</label>
                            <input type="text" name="description" class="form-control bg-black text-white">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Tags</label>
                            <input type="text" name="tags" class="form-control bg-black text-white" placeholder="bv. extern, beta, intern">
                            <div class="form-text text-muted">Komma gescheiden labels voor filtering.</div>
                        </div>
                    </div>
                    <div class="modal-footer border-secondary">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annuleren</button>
                        <button type="submit" class="btn btn-primary">Aanmaken</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    
    <div class="modal fade" id="editEndpointModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content bg-dark text-white border-secondary">
                <div class="modal-header border-secondary">
                    <h5 class="modal-title">Endpoint Bewerken</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <form method="POST" action="/endpoints/update">
                    <div class="modal-body">
                        <div class="mb-3">
                            <label class="form-label">Naam</label>
                            <input type="text" id="edit-name-display" class="form-control bg-secondary text-white" disabled>
                            <input type="hidden" name="name" id="edit-name-input">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Omschrijving</label>
                            <input type="text" name="description" id="edit-desc-input" class="form-control bg-black text-white">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Tags</label>
                            <input type="text" name="tags" id="edit-tags-input" class="form-control bg-black text-white" placeholder="bv. extern, beta">
                        </div>
                    </div>
                    <div class="modal-footer border-secondary">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annuleren</button>
                        <button type="submit" class="btn btn-primary">Opslaan</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    
    <script>
    function openEditModal(name, desc, tags) {
        document.getElementById('edit-name-display').value = name;
        document.getElementById('edit-name-input').value = name;
        document.getElementById('edit-desc-input').value = desc;
        document.getElementById('edit-tags-input').value = tags;
        
        var myModal = new bootstrap.Modal(document.getElementById('editEndpointModal'));
        myModal.show();
    }
    </script>
"""

CLIENT_DETAIL_CONTENT = """
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2>Client: <span class="text-info">{{ source_app }}</span></h2>
        <a href="/" class="btn btn-secondary"><i class="bi bi-arrow-left"></i> Terug</a>
    </div>
    
    <div class="row mb-4">
        <div class="col-md-6">
            <div class="card p-3">
                <h5 class="text-muted">Requests (Laatste 24u)</h5>
                <h3 class="mt-2 text-primary">{{ total_requests }}</h3>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card p-3">
                <h5 class="text-muted">Authenticatie</h5>
                <div class="mt-2">
                    {% if is_user %}
                        <span class="badge bg-primary fs-5"><i class="bi bi-person-fill"></i> Logged in User (JWT)</span>
                    {% elif has_key %}
                        <span class="badge bg-success fs-5"><i class="bi bi-key-fill"></i> API Key Actief</span>
                    {% else %}
                        <span class="badge bg-danger fs-5"><i class="bi bi-exclamation-triangle-fill"></i> Geen Key</span>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>

    <div class="card p-4">
        <h5 class="card-title mb-3">Laatste 20 Logregels</h5>
        <table class="table table-dark table-striped table-hover">
            <thead>
                <tr>
                    <th>Tijd (Lokaal)</th>
                    <th>Actie</th>
                    <th>Endpoint</th>
                </tr>
            </thead>
            <tbody>
                {% for log in logs %}
                <tr>
                    <td class="utc-timestamp log-timestamp" data-utc="{{ log.timestamp }}"></td>
                    <td>{{ log.action }}</td>
                    <td><span class="badge bg-secondary">{{ log.endpoint }}</span></td>
                </tr>
                {% else %}
                <tr><td colspan="3" class="text-center text-muted">Geen logs.</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
"""

SETTINGS_CONTENT = """
    <h2>Instellingen</h2>
    <div class="row mt-4">
        <div class="col-md-6">
            <div class="card p-4">
                <h5>Nieuwe Gebruiker Aanmaken</h5>
                <form method="POST" action="/settings">
                    <div class="mb-3">
                        <label class="form-label text-muted">Naam</label>
                        <input type="text" name="username" class="form-control bg-dark text-white" placeholder="Gebruikersnaam" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-muted">Wachtwoord</label>
                        <input type="password" name="password" class="form-control bg-dark text-white" placeholder="Wachtwoord" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label text-muted">Token Geldigheid</label>
                        <select name="token_validity_minutes" class="form-select bg-dark text-white">
                            <option value="1440" selected>24 uur</option>
                            <option value="10080">7 dagen</option>
                            <option value="44640">31 dagen</option>
                            <option value="525600">365 dagen</option>
                        </select>
                        <div class="form-text text-muted small">Dit geldt voor het eerste token én toekomstige logins.</div>
                    </div>
                    <button type="submit" name="action" value="create_user" class="btn btn-success">Gebruiker Toevoegen</button>
                </form>
            </div>
            
            <div class="card p-4 mt-3">
                 <h5>Database Connection</h5>
                 <form method="POST" action="/settings">
                    <div class="mb-3">
                        <input type="text" name="mongo_uri" class="form-control bg-dark text-white" value="{{ current_uri }}">
                    </div>
                    <button type="submit" name="action" value="save_uri" class="btn btn-primary">Opslaan & Testen</button>
                 </form>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card p-4 mb-3">
                <h5>Actieve Gebruikers (JWT)</h5>
                <ul class="list-group list-group-flush">
                    {% for user in active_users %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between">
                        <div>
                            {{ user.username }} 
                            <small class="text-muted d-block" style="font-size: 0.8em">
                                Sinds: <span class="utc-timestamp" data-utc="{{ user.created_at.isoformat() }}"></span><br>
                                Token duur: {{ (user.validity / 60) | int }} uur
                            </small>
                        </div>
                        <form method="POST" action="/settings" onsubmit="return confirm('Gebruiker \'{{ user.username }}\' verwijderen? Dit verbreekt alle actieve JWTs van deze gebruiker!');">
                            <input type="hidden" name="action" value="delete_user">
                            <input type="hidden" name="username" value="{{ user.username }}">
                            <button class="btn btn-sm btn-danger ms-2">X</button>
                        </form>
                    </li>
                    {% else %}
                    <li class="list-group-item bg-transparent text-muted">Geen gebruikers gevonden.</li>
                    {% endfor %}
                </ul>
            </div>
            <div class="card p-4">
                <h5>Actieve API Sleutels (Legacy)</h5>
                <ul class="list-group list-group-flush">
                    {% for id, data in api_keys.items() %}
                    <li class="list-group-item bg-transparent text-white d-flex justify-content-between align-items-start">
                        <div class="me-3 flex-grow-1">
                            <div>{{ data.description }} <small class="text-muted">({{ id }})</small></div>
                            <div class="input-group input-group-sm mt-1">
                                <input type="text" class="form-control bg-dark text-warning small font-monospace" readonly 
                                    value="{{ data.key }}" id="key-{{ id }}">
                                <button type="button" class="btn btn-outline-info" 
                                        onclick="copyKey('key-{{ id }}')" title="Kopieer Key">
                                    <i class="bi bi-clipboard"></i>
                                </button>
                            </div>
                        </div>
                        <form method="POST" action="/settings" onsubmit="return confirm('Intrekken?');">
                            <input type="hidden" name="action" value="revoke_key">
                            <input type="hidden" name="client_id" value="{{ id }}">
                            <button class="btn btn-sm btn-danger ms-2" title="Trek in">X</button>
                        </form>
                    </li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>
"""
