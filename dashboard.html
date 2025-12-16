<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>G2 API Dashboard</title>
    <!-- Laad Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Iconen: Lucide Icons -->
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        body {
            font-family: 'Inter', sans-serif;
            background-color: #f7f7f7;
            min-height: 100vh;
        }
        .card {
            background-color: white;
            border-radius: 0.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.06);
        }
        .btn-primary {
            background-color: #10b981; /* Emerald 500 */
            color: white;
            transition: background-color 0.15s;
        }
        .btn-primary:hover {
            background-color: #059669; /* Emerald 600 */
        }
        .btn-danger {
            background-color: #ef4444; /* Red 500 */
            color: white;
            transition: background-color 0.15s;
        }
        .btn-danger:hover {
            background-color: #dc2626; /* Red 600 */
        }
        /* Custom scrollbar for better look */
        ::-webkit-scrollbar {
            width: 8px;
        }
        ::-webkit-scrollbar-thumb {
            background: #d1d5db;
            border-radius: 10px;
        }
    </style>
</head>
<body class="flex flex-col">

    <div id="app" class="flex-grow">
        <!-- Login Scherm -->
        <div id="login-screen" class="min-h-screen flex items-center justify-center bg-gray-100">
            <div class="card p-8 w-full max-w-md">
                <h2 class="text-3xl font-bold mb-6 text-center text-gray-800">API Dashboard Login</h2>
                <div id="login-message" class="p-3 mb-4 rounded-lg text-sm hidden"></div>
                <form id="login-form" class="space-y-4">
                    <div>
                        <label for="username" class="block text-sm font-medium text-gray-700">Gebruikersnaam</label>
                        <input type="text" id="username" value="admin" class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-emerald-500 focus:border-emerald-500">
                    </div>
                    <div>
                        <label for="password" class="block text-sm font-medium text-gray-700">Wachtwoord</label>
                        <input type="password" id="password" value="[admin-wachtwoord]" class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-emerald-500 focus:border-emerald-500">
                    </div>
                    <button type="submit" class="btn-primary w-full py-2 px-4 rounded-md font-semibold">Inloggen</button>
                </form>
            </div>
        </div>

        <!-- Dashboard Scherm -->
        <div id="dashboard-screen" class="hidden">
            <header class="bg-gray-800 text-white p-4 shadow-md">
                <div class="max-w-7xl mx-auto flex justify-between items-center">
                    <h1 class="text-2xl font-bold">G2 API Beheerpaneel</h1>
                    <div class="flex items-center space-x-4">
                        <span id="user-display" class="text-sm font-medium"></span>
                        <button id="logout-btn" class="text-sm py-1 px-3 bg-red-600 rounded hover:bg-red-700 transition">Uitloggen</button>
                    </div>
                </div>
            </header>

            <main class="max-w-7xl mx-auto p-6 space-y-8">
                
                <!-- Statistieken Overzicht -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div class="card p-6 border-t-4 border-emerald-500">
                        <p class="text-sm text-gray-500">Actieve Endpoints</p>
                        <p id="stat-endpoints" class="text-3xl font-bold text-gray-900 mt-1">...</p>
                    </div>
                    <div class="card p-6 border-t-4 border-blue-500">
                        <p class="text-sm text-gray-500">Geregistreerde Clients</p>
                        <p id="stat-clients" class="text-3xl font-bold text-gray-900 mt-1">...</p>
                    </div>
                    <div class="card p-6 border-t-4 border-yellow-500">
                        <p class="text-sm text-gray-500">Totaal API Calls</p>
                        <p id="stat-calls" class="text-3xl font-bold text-gray-900 mt-1">...</p>
                    </div>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <!-- API Key Beheer -->
                    <div class="card p-6 lg:col-span-2">
                        <h3 class="text-xl font-semibold mb-4 border-b pb-2">API Sleutel Beheer</h3>
                        <div id="settings-message" class="p-3 mb-4 rounded-lg text-sm hidden"></div>

                        <form id="generate-key-form" class="flex space-x-3 mb-6">
                            <input type="text" id="new-key-desc" placeholder="Beschrijving (bijv. 'Frontend App')" required class="flex-grow px-3 py-2 border border-gray-300 rounded-md shadow-sm">
                            <button type="submit" class="btn-primary py-2 px-4 rounded-md font-semibold">Genereer Nieuwe Sleutel</button>
                        </form>

                        <div class="overflow-x-auto">
                            <table class="min-w-full divide-y divide-gray-200">
                                <thead>
                                    <tr>
                                        <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/4">Beschrijving</th>
                                        <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/4">Client ID</th>
                                        <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/2">API Key</th>
                                        <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Acties</th>
                                    </tr>
                                </thead>
                                <tbody id="api-keys-table" class="bg-white divide-y divide-gray-200">
                                    <!-- Key rijen worden hier geladen door JS -->
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Activiteit en Gebruik -->
                    <div class="card p-6 lg:col-span-1">
                        <h3 class="text-xl font-semibold mb-4 border-b pb-2">Recente API Activiteit</h3>
                        <ul id="activity-list" class="space-y-3 text-sm">
                            <!-- Activiteit wordt hier geladen door JS -->
                        </ul>
                    </div>
                </div>
            </main>
        </div>
    </div>

    <script>
        // FIX: Gebruik een relatieve URL /api in plaats van de hardgecodeerde 127.0.0.1:5000
        const API_BASE_URL = '/api'; 
        
        // --- DOM Selectors ---
        const loginScreen = document.getElementById('login-screen');
        const dashboardScreen = document.getElementById('dashboard-screen');
        const loginForm = document.getElementById('login-form');
        const loginMessage = document.getElementById('login-message');
        const logoutBtn = document.getElementById('logout-btn');
        const userDisplay = document.getElementById('user-display');
        const statEndpoints = document.getElementById('stat-endpoints');
        const statClients = document.getElementById('stat-clients');
        const statCalls = document.getElementById('stat-calls');
        const apiKeysTable = document.getElementById('api-keys-table');
        const generateKeyForm = document.getElementById('generate-key-form');
        const settingsMessage = document.getElementById('settings-message');
        const activityList = document.getElementById('activity-list');

        let currentUserId = null;

        // --- Hulpfuncties ---
        function showMessage(element, text, isError = false) {
            element.textContent = text;
            element.className = `p-3 mb-4 rounded-lg text-sm ${isError ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`;
            element.style.display = 'block';
        }

        function hideMessage(element) {
            element.style.display = 'none';
        }

        function toggleScreens(isLoggedIn) {
            if (isLoggedIn) {
                loginScreen.classList.add('hidden');
                dashboardScreen.classList.remove('hidden');
            } else {
                loginScreen.classList.remove('hidden');
                dashboardScreen.classList.add('hidden');
            }
        }

        async function safeFetch(path, options = {}) { // path is nu relatief aan API_BASE_URL
            // FIX: Concateneer API_BASE_URL met het pad
            const url = `${API_BASE_URL}${path}`;

            // Deze functie stuurt automatisch de JWT cookie mee
            options.credentials = 'include';
            options.headers = {
                'Content-Type': 'application/json',
                ...options.headers
            };

            try {
                const response = await fetch(url, options);
                let data = null;
                try {
                    data = await response.json();
                } catch (e) {
                    // Soms stuurt de API geen JSON terug (bv. bij 200/204)
                }

                if (!response.ok) {
                    // Vang 401 Unauthorized op om de gebruiker uit te loggen
                    if (response.status === 401) {
                        handleLogout(true);
                        throw new Error("Sessie verlopen. Log opnieuw in.");
                    }
                    throw new Error(data?.error || data?.message || `Fout: HTTP Status ${response.status}`);
                }
                return data;

            } catch (error) {
                console.error("Fetch Error:", error);
                throw error;
            }
        }

        // --- Authenticatie Handlers ---

        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            hideMessage(loginMessage);

            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            try {
                // Pad is nu /login
                const response = await safeFetch('/login', {
                    method: 'POST',
                    body: JSON.stringify({ username, password })
                });

                // De succesvolle respons bevat geen data (alleen de cookie)
                if (response && response.message) {
                    // De browser heeft nu de HTTP-only cookie, laad het dashboard
                    loadDashboard();
                }

            } catch (error) {
                showMessage(loginMessage, error.message, true);
            }
        });

        logoutBtn.addEventListener('click', () => handleLogout(false));

        async function handleLogout(isSessionExpired) {
            try {
                // Roep de logout API aan om de cookie te wissen
                await safeFetch('/logout', { method: 'POST' });
            } catch (e) {
                // Negeer fouten, we gaan toch uitloggen
            }
            toggleScreens(false);
            showMessage(loginMessage, isSessionExpired ? 'Sessie verlopen. Log opnieuw in.' : 'U bent uitgelogd.', !isSessionExpired);
            userDisplay.textContent = '';
        }

        // --- Dashboard Data Laden ---

        async function loadDashboard() {
            try {
                const dashboardData = await safeFetch('/dashboard');
                const settingsData = await safeFetch('/settings');

                // Toon scherm
                toggleScreens(true);

                // Dashboard Samenvatting
                currentUserId = dashboardData.user_id;
                userDisplay.textContent = `Ingelogd als: ${dashboardData.user_id}`;
                statEndpoints.textContent = dashboardData.summary.endpoints_count;
                statClients.textContent = dashboardData.summary.clients_count;
                statCalls.textContent = dashboardData.summary.calls_count;

                // Recente Activiteit
                renderActivity(dashboardData.recent_activity);
                
                // API Keys
                renderApiKeys(settingsData.api_keys);

            } catch (error) {
                // Als het laden mislukt (meestal 401), dan wordt handleLogout al aangeroepen in safeFetch
                console.error("Dashboard laadfout:", error);
                if (!currentUserId) { // Zorg ervoor dat we teruggaan naar login als er een echte fout is
                    toggleScreens(false);
                    // Geen bericht hier, want safeFetch toont al de "Sessie verlopen" melding
                }
            }
        }

        // --- Rendering Functies ---

        function renderActivity(activity) {
            activityList.innerHTML = '';
            if (activity.length === 0) {
                activityList.innerHTML = '<li class="text-gray-500">Nog geen recente activiteit.</li>';
                return;
            }

            activity.forEach(log => {
                const date = new Date(log.timestamp).toLocaleTimeString();
                const item = document.createElement('li');
                item.className = 'border-b border-gray-100 pb-2';
                item.innerHTML = `
                    <span class="font-mono text-xs text-gray-400">${date}</span>
                    <p class="text-gray-800">${log.action.toUpperCase()} op 
                        <span class="font-semibold text-emerald-600">${log.endpoint}</span> 
                        (Client: ${log.client_id})
                    </p>
                `;
                activityList.appendChild(item);
            });
        }

        function renderApiKeys(keys) {
            apiKeysTable.innerHTML = '';

            if (keys.length === 0) {
                apiKeysTable.innerHTML = `<tr><td colspan="4" class="px-3 py-2 text-center text-gray-500">Geen actieve API sleutels gevonden.</td></tr>`;
                return;
            }
            
            keys.forEach(client => {
                const row = document.createElement('tr');
                row.className = 'hover:bg-gray-50';
                
                row.innerHTML = `
                    <td class="px-3 py-2 whitespace-nowrap text-sm font-medium text-gray-900">${client.description}</td>
                    <td class="px-3 py-2 whitespace-nowrap text-sm text-gray-500 font-mono">${client.client_id}</td>
                    <td class="px-3 py-2 text-sm font-mono flex items-center">
                        <input type="text" value="${client.key}" readonly class="text-xs bg-gray-100 border-none rounded-md p-1 w-full" id="key-${client.client_id}">
                        <button class="ml-2 text-gray-500 hover:text-gray-800" onclick="copyToClipboard('key-${client.client_id}', this)" title="Kopieer">
                            <svg class="w-4 h-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                        </button>
                    </td>
                    <td class="px-3 py-2 whitespace-nowrap text-right text-sm font-medium">
                        <button class="btn-danger text-xs py-1 px-2 rounded" onclick="revokeKey('${client.client_id}')">Trek in</button>
                    </td>
                `;
                apiKeysTable.appendChild(row);
            });
        }

        // Global functie voor kopiëren (gebruikt in de innerHTML)
        window.copyToClipboard = function(elementId, button) {
            const copyText = document.getElementById(elementId);
            copyText.select();
            copyText.setSelectionRange(0, 99999); 
            document.execCommand('copy');
            
            const originalText = button.innerHTML;
            button.innerHTML = '<span class="text-green-500">Gekopieerd!</span>';
            setTimeout(() => {
                button.innerHTML = originalText;
            }, 1500);
        };

        // --- Key Beheer Handlers ---

        generateKeyForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            hideMessage(settingsMessage);

            const description = document.getElementById('new-key-desc').value;

            try {
                // Pad is nu /settings
                const response = await safeFetch('/settings', {
                    method: 'POST',
                    body: JSON.stringify({ description })
                });

                showMessage(settingsMessage, `Sleutel voor '${description}' gegenereerd. ID: ${response.client_id}`, false);
                document.getElementById('new-key-desc').value = '';
                loadDashboard(); // Herlaad data inclusief nieuwe key

            } catch (error) {
                showMessage(settingsMessage, `Fout bij genereren: ${error.message}`, true);
            }
        });

        window.revokeKey = async function(clientId) {
            // Gebruik een custom modal of console log in plaats van confirm()
            if (!confirm(`Weet u zeker dat u Client ID ${clientId} wilt intrekken? Dit is onomkeerbaar!`)) {
                return;
            }
            hideMessage(settingsMessage);

            try {
                // Pad is nu /settings
                await safeFetch('/settings', {
                    method: 'DELETE',
                    body: JSON.stringify({ client_id: clientId })
                });

                showMessage(settingsMessage, `Client ID ${clientId} succesvol ingetrokken.`, false);
                loadDashboard(); 

            } catch (error) {
                showMessage(settingsMessage, `Fout bij intrekken: ${error.message}`, true);
            }
        };


        // --- Initialisatie ---

        // Controleer of de gebruiker al ingelogd is (door de cookie te proberen te gebruiken)
        // We proberen het dashboard te laden; als de cookie ontbreekt/verlopen is, zal safeFetch falen en de login tonen.
        loadDashboard(); 
        
    </script>
</body>
</html>
