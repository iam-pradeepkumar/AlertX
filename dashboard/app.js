/**
 * AlertX | Professional Dashboard Logic
 */

const getBaseUrl = () => {
    const origin = window.location.origin;
    const path = window.location.pathname.replace(/\/+$/, '');
    const base = path.endsWith('/dashboard') ? path.slice(0, -10) : path;
    return origin + base;
};
const API_BASE = getBaseUrl();
console.log("AlertX: System initialized at", API_BASE);
let token = localStorage.getItem('alertx_token');
let lastEventId = -1;
let map = null;
let userPos = [12.9716, 77.5946]; // Default (Bangalore)
let isLive = false;
let pollingIntervals = [];
let isLoggingOut = false;
let browserStream = null;      // MediaStream from browser webcam
let browserCamInterval = null; // Interval for frame capture loop
let isBrowserCamMode = false;  // True when using browser webcam fallback

// ── AUTHENTICATION ────────────────────────────────

async function apiRequest(endpoint, method = 'GET', body = null, isForm = false) {
    const headers = {};
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    let options = { method, headers };
    
    if (body) {
        if (isForm) {
            const formData = new URLSearchParams();
            for (const key in body) formData.append(key, body[key]);
            options.body = formData;
            headers['Content-Type'] = 'application/x-www-form-urlencoded';
        } else {
            options.body = JSON.stringify(body);
            headers['Content-Type'] = 'application/json';
        }
    }

    try {
        const response = await fetch(`${API_BASE}${endpoint}`, options);
        
        if (response.status === 401) {
            if (endpoint !== '/auth/login') {
                logout();
                throw new Error("Session expired. Please login again.");
            } else {
                throw new Error("Invalid username or password.");
            }
        }
        
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Request failed");
        }
        return data;
    } catch (err) {
        console.error(`AlertX API Error (${endpoint}):`, err);
        throw err;
    }
}

function login(username, password) {
    apiRequest('/auth/login', 'POST', { username, password }, true)
        .then(data => {
            token = data.access_token;
            localStorage.setItem('alertx_token', token);
            showApp();
            showToast("Welcome back, Commander.", "success");
        })
        .catch(err => showToast(err.message, "error"));
}

function signup(username, email, password) {
    // Better compatibility: Send as JSON body
    apiRequest('/auth/signup', 'POST', { username, email, password })
        .then(() => {
            showToast("Account created successfully. Please login.", "success");
            switchOverlay('auth-overlay');
        })
        .catch(err => {
            console.error("Signup failed:", err);
            showToast(`Signup Failed: ${err.message}`, "error");
        });
}

function logout() {
    if (isLoggingOut) return;
    isLoggingOut = true;
    
    if (!token && !localStorage.getItem('alertx_token')) {
        isLoggingOut = false;
        return;
    }
    
    // Stop polling
    pollingIntervals.forEach(clearInterval);
    pollingIntervals = [];
    
    // Stop feed first while we still have the token
    if (isLive) {
        // Use a local copy of token for the request
        const currentToken = token;
        stopFeed();
    }
    
    token = null;
    localStorage.removeItem('alertx_token');
    document.getElementById('app-shell').classList.add('hidden');
    document.getElementById('auth-overlay').classList.add('active');
    
    isLoggingOut = false;
}

function showApp() {
    document.getElementById('auth-overlay').classList.remove('active');
    document.getElementById('signup-overlay').classList.remove('active');
    document.getElementById('app-shell').classList.remove('hidden');
    
    // Get user info
    apiRequest('/auth/me').then(user => {
        document.getElementById('user-display').textContent = user.username;
    });
    
    initPolling();
}

// ── UI NAVIGATION ────────────────────────────────

function switchView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    
    document.getElementById(`view-${viewName}`).classList.add('active');
    document.querySelector(`[data-view="${viewName}"]`).classList.add('active');
    
    if (viewName === 'live-map') {
        initMap();
    } else if (viewName === 'history') {
        updateHistory();
    }
}

function switchOverlay(overlayId) {
    document.querySelectorAll('.overlay').forEach(o => o.classList.remove('active'));
    document.getElementById(overlayId).classList.add('active');
}

// ── MAP & LOCATION ───────────────────────────────

function initMap() {
    if (map) return;
    
    map = L.map('map').setView(userPos, 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Dark mode map filter
    document.querySelector('.leaflet-container').style.filter = "invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%)";

    // Detect user location
    const defaultFallback = () => {
        console.warn("Using default simulated location.");
        findNearbyServices(userPos);
    };

    const applyLocation = (lat, lon) => {
        userPos = [lat, lon];
        map.setView(userPos, 14);
        L.marker(userPos).addTo(map).bindPopup("Active Security Node").openPopup();
        findNearbyServices(userPos);
    };

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            pos => applyLocation(pos.coords.latitude, pos.coords.longitude),
            async err => {
                console.warn("Browser GPS blocked. Attempting IP triangulation...");
                try {
                    const res = await fetch("https://ipapi.co/json/");
                    const data = await res.json();
                    if (data.latitude && data.longitude) applyLocation(data.latitude, data.longitude);
                    else defaultFallback();
                } catch { defaultFallback(); }
            },
            { timeout: 5000 }
        );
    } else {
        async function fetchIP() {
            try {
                const res = await fetch("https://ipapi.co/json/");
                const data = await res.json();
                if (data.latitude) applyLocation(data.latitude, data.longitude);
                else defaultFallback();
            } catch { defaultFallback(); }
        }
        fetchIP();
    }
}

function findNearbyServices(pos) {
    // Simulated nearby services (mocked for production look)
    const services = [
        { name: "City Central Police", type: "police", dist: "1.2km", icon: "👮" },
        { name: "Metro General Hospital", type: "ambulance", dist: "2.4km", icon: "🚑" },
        { name: "Fire Station #4", type: "fire", dist: "0.8km", icon: "🚒" },
        { name: "St. Jude Clinic", type: "ambulance", dist: "3.1km", icon: "🏥" },
        { name: "East Side Precinct", type: "police", dist: "4.5km", icon: "🚓" }
    ];
    
    const container = document.getElementById('nearby-services');
    container.innerHTML = services.map(s => `
        <div class="service-card">
            <div class="service-icon">${s.icon}</div>
            <div class="service-info">
                <h4>${s.name}</h4>
                <p>${s.type.toUpperCase()} • ${s.dist}</p>
            </div>
        </div>
    `).join('');
}

// ── UPLOAD LOGIC ────────────────────────────────

async function handleUpload(file) {
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    const progressContainer = document.getElementById('upload-progress-container');
    const content = document.getElementById('upload-content');
    const progressBar = document.getElementById('upload-progress');
    const status = document.getElementById('upload-status');
    
    progressContainer.classList.remove('hidden');
    content.classList.add('hidden');
    status.innerHTML = `<span class="spinner-sm"></span> Uploading ${file.name}...`;

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });
        
        if (!response.ok) throw new Error("Upload failed");
        
        const data = await response.json();
        
        // Show the video in playback
        const playback = document.getElementById('video-playback');
        const feed = document.getElementById('video-feed');
        const placeholder = document.getElementById('feed-placeholder');
        
        playback.src = `/media/${data.filename}`;
        playback.classList.remove('hidden');
        feed.classList.add('hidden');
        placeholder.classList.add('hidden');
        playback.play();

        status.innerHTML = `<span class="text--accent">✓</span> Analyzing video...`;
        
        // Trigger Analysis
        const result = await apiRequest(`/analyze?filename=${data.filename}`, 'POST');
        status.innerHTML = `<span class="text--online">✓ Analysis Complete</span>`;
        showToast("Video analysis finished.", "success");
        updateEvents();
        
        setTimeout(() => {
            progressContainer.classList.add('hidden');
            content.classList.remove('hidden');
            status.innerHTML = "";
        }, 3000);
        
    } catch (e) {
        showToast(e.message, "error");
        status.innerHTML = `<span class="text--critical">Error</span>`;
    }
}

// ── CORE MONITORING ──────────────────────────────

function initPolling() {
    pollingIntervals.forEach(clearInterval);
    pollingIntervals = [];

    updateStatus();
    updateEvents();
    
    pollingIntervals.push(setInterval(updateStatus, 12000));
    pollingIntervals.push(setInterval(updateEvents, 10000));
}

async function updateStatus() {
    try {
        const data = await apiRequest('/status');
        const emailInput = document.getElementById('alert-email');
        if (emailInput && document.activeElement !== emailInput) {
            emailInput.value = data.alert_recipient || "";
        }
        
        const eventData = await apiRequest('/events?limit=100');
        const events = eventData.events || [];
        
        document.getElementById('stat-total').textContent = events.length;
        
        const critical = events.filter(e => e.priority === 'CRITICAL').length;
        const high = events.filter(e => e.priority === 'HIGH').length;
        document.getElementById('stat-critical').textContent = critical;
        document.getElementById('stat-high').textContent = high;
        
        const statusMsg = document.getElementById('system-status-msg');
        if (statusMsg) {
            const dbBadge = data.db_mode === "Cloud (Firebase)" ? 
                '<span style="color: #10b981; font-weight: bold;">[☁️ Firebase Active]</span>' : 
                '<span style="color: #f59e0b; font-weight: bold;">[💾 Local Mode]</span>';
            statusMsg.innerHTML = (data.camera_active ? "AI Node Online " : "AI Node Standby ") + dbBadge;
        }

        // AUTO-VIEW: If a camera is active elsewhere, show it here too
        if (data.camera_active && !isLive) {
            console.log("AlertX: Active node detected on another device. Syncing feed...");
            const authData = await apiRequest('/auth/stream-token', 'POST', null, true);
            const ticket = authData.ticket;
            const feed = document.getElementById('video-feed');
            const placeholder = document.getElementById('feed-placeholder');
            const btn = document.getElementById('btn-start');

            feed.src = `${API_BASE}/video_feed?ticket=${ticket}&t=${new Date().getTime()}`;
            feed.classList.remove('hidden');
            placeholder.classList.add('hidden');
            isLive = true;
            btn.textContent = "Node Online";
        }
    } catch (e) { console.error(e); }
}

async function updateEvents() {
    try {
        const filter = document.getElementById('filter-type').value;
        const url = `/events?limit=25${filter ? '&incident_type=' + filter : ''}`;
        
        const data = await apiRequest(url);
        const events = data.events || [];
        
        // Performance: Only redraw if there's a CHANGE
        const newHash = events.map(e => e.id).join(',');
        if (window._lastEventHash === newHash) return;
        window._lastEventHash = newHash;

        const container = document.getElementById('event-list');
        
        container.innerHTML = events.map(e => {
            let mediaPath = e.media_path;
            if (!mediaPath && e.source && e.source.startsWith('upload:')) {
                mediaPath = '/media/' + e.source.split(':')[1];
            }
            return `
            <li class="event-item" onclick="playEvidence('${mediaPath || ''}', '${e.id}')">
                <div class="event-item__time">${new Date(e.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}</div>
                <div class="event-item__content">
                    <span class="event-item__tag tag--${e.priority.toLowerCase()}">${e.priority} ${e.incident_type.toUpperCase()}</span>
                    <div class="event-item__title">${e.description || e.details || 'Incident detected'}</div>
                </div>
            </li>
            `;
        }).join('');
    } catch (e) { console.error(e); }
}

async function updateHistory() {
    try {
        const data = await apiRequest('/events?limit=200');
        const list = document.getElementById('history-list');
        if (!list) return;

        if (!data.events || data.events.length === 0) {
            list.innerHTML = `<li style="padding: 2rem; text-align: center; color: var(--text-secondary);">No forensic evidence found in the active archive.</li>`;
            return;
        }
        
        list.innerHTML = (data.events || []).map(e => {
            let mediaPath = e.media_path;
            if (!mediaPath && e.source && e.source.startsWith('upload:')) {
                mediaPath = '/media/' + e.source.split(':')[1];
            }
            return `
            <li class="event-item" onclick="playEvidence('${mediaPath || ''}', '${e.id}')">
                <div class="event-item__time">${new Date(e.timestamp).toLocaleString()}</div>
                <div class="event-item__content">
                    <span class="event-item__tag tag--${e.priority.toLowerCase()}">${e.priority} ${e.incident_type.toUpperCase()}</span>
                    <div class="event-item__title">${e.description || e.details || 'Incident detected'}</div>
                    <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:0.5rem">Source: ${e.source} | Frame ID: ${e.frame_index}</div>
                </div>
            </li>
            `;
        }).join('');
    } catch(e) { console.error(e); }
}

function playEvidence(path, id) {
    if (!path || path === "null" || path === "undefined") {
        showToast("No evidence media attached.", "error");
        return;
    }
    
    // Switch to dashboard view
    switchView('dashboard');
    
    // Switch to playback view
    const playback = document.getElementById('video-playback');
    const imagePlayback = document.getElementById('image-playback');
    const feed = document.getElementById('video-feed');
    const placeholder = document.getElementById('feed-placeholder');
    
    if (path.endsWith('.jpg') || path.endsWith('.png')) {
        imagePlayback.src = path;
        imagePlayback.classList.remove('hidden');
        playback.classList.add('hidden');
    } else {
        playback.src = path;
        playback.classList.remove('hidden');
        if (imagePlayback) imagePlayback.classList.add('hidden');
        playback.play();
    }
    
    feed.classList.add('hidden');
    placeholder.classList.add('hidden');
    
    showToast("Viewing digital evidence...", "info");
}

async function startFeed() {
    const feed = document.getElementById('video-feed');
    const playback = document.getElementById('video-playback');
    const placeholder = document.getElementById('feed-placeholder');
    const btn = document.getElementById('btn-start');
    
    btn.textContent = "Initializing...";
    btn.disabled = true;
    
    // Hide any previous playback
    playback.classList.add('hidden');
    playback.src = "";
    const imagePlayback = document.getElementById('image-playback');
    if (imagePlayback) imagePlayback.classList.add('hidden');

    // ── STRATEGY 1: Try server-side camera (works locally or with remote URL) ──
    const source = document.getElementById('cam-source').value.trim();
    if (source && source !== "0") {
        try {
            console.log(`AlertX: Attempting to start camera with source: ${source}`);
            await apiRequest(`/camera/start?source=${encodeURIComponent(source)}`, 'POST', null, true);
            
            // Server camera worked — use MJPEG stream
            const authData = await apiRequest('/auth/stream-token', 'POST', null, true);
            const ticket = authData.ticket;

            // Always use the server-proxied stream to avoid Mixed Content errors (HTTPS -> HTTP)
            // and to ensure AI bounding boxes are visible on the feed.
            feed.src = `${API_BASE}/video_feed?ticket=${ticket}&t=${new Date().getTime()}`;

            feed.classList.remove('hidden');
            placeholder.classList.add('hidden');
            isLive = true;
            isBrowserCamMode = false;
            feed.onload = () => { btn.textContent = "Node Online"; };
            showToast("Server camera connected", "success");
            return;
        } catch (e) {
            console.warn("AlertX: Server camera unavailable, trying browser webcam...", e.message);
        }
    }

    // ── STRATEGY 2: Browser webcam fallback (works on cloud) ──
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error("Browser does not support camera access");
        }

        console.log("AlertX: Server camera failed, initiating browser-side fallback...");
        showToast("Server has no camera. Switching to browser webcam...", "info");

        browserStream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "environment" },
            audio: false
        });

        const browserCam = document.getElementById('browser-cam');
        const canvas = document.getElementById('browser-canvas');
        const ctx = canvas.getContext('2d');

        browserCam.srcObject = browserStream;
        const overlay = document.getElementById('overlay-canvas');
        const overlayCtx = overlay.getContext('2d');
        const camContainer = document.getElementById('browser-cam-container');
        
        camContainer.classList.remove('hidden');
        feed.classList.add('hidden');
        placeholder.classList.add('hidden');

        // Robust wait for video metadata
        if (browserCam.readyState >= 2) {
            canvas.width = 640; // Detection resolution
            canvas.height = 480;
            overlay.width = browserCam.videoWidth;
            overlay.height = browserCam.videoHeight;
        } else {
            await new Promise((resolve) => {
                browserCam.onloadedmetadata = () => {
                    canvas.width = 640;
                    canvas.height = 480;
                    overlay.width = browserCam.videoWidth;
                    overlay.height = browserCam.videoHeight;
                    resolve();
                };
            });
        }

        await browserCam.play();
        isLive = true;
        isBrowserCamMode = true;
        btn.textContent = "Browser Cam Live";
        btn.disabled = false;

        let isProcessing = false;
        
        setTimeout(() => {
            browserCamInterval = setInterval(async () => {
            if (!isLive || !isBrowserCamMode || isProcessing) return;

            isProcessing = true;
            try {
                // Capture frame for AI (scaled down to 640px for speed)
                ctx.drawImage(browserCam, 0, 0, canvas.width, canvas.height);
                const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.6));
                if (!blob) { isProcessing = false; return; }

                const formData = new FormData();
                formData.append('file', blob, 'frame.jpg');

                const response = await fetch(`${API_BASE}/process_frame`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });

                if (!response.ok) throw new Error('AI Sync Failed');
                const data = await response.json();

                // ── DRAW BOXES (Client Side) ──
                overlayCtx.clearRect(0, 0, overlay.width, overlay.height);
                
                // Scale factor between detection size (640x480) and display size
                const scaleX = overlay.width / canvas.width;
                const scaleY = overlay.height / canvas.height;

                if (data.detections) {
                    data.detections.forEach(det => {
                        const [x1, y1, x2, y2] = det.box;
                        const color = det.type ? "#ff4d4d" : "#00ff88"; // Red for incidents, Green for info
                        
                        overlayCtx.strokeStyle = color;
                        overlayCtx.lineWidth = 3;
                        overlayCtx.strokeRect(x1 * scaleX, y1 * scaleY, (x2-x1) * scaleX, (y2-y1) * scaleY);

                        overlayCtx.fillStyle = color;
                        overlayCtx.font = "bold 16px Inter, sans-serif";
                        overlayCtx.fillText(`${det.label} ${Math.round(det.conf*100)}%`, x1 * scaleX, y1 * scaleY - 10);
                    });
                }

                if (data.incidents && data.incidents.length > 0) {
                    data.incidents.forEach(inc => showToast(`🚨 ${inc.type.toUpperCase()}!`, "error"));
                    updateEvents();
                }
            } catch (err) {
                console.warn("AI Loop Error:", err);
            } finally {
                isProcessing = false;
            }
        }, 300); // 3 FPS detection (Video remains 30FPS)
    }, 1000);

    showToast("Browser webcam active — AI processing enabled", "success");

    } catch (camErr) {
        console.error("AlertX: Browser camera initialization failed:", camErr);
        showToast("Camera failed: " + camErr.message, "error");
        btn.textContent = "Start Node";
        btn.disabled = false;
    }
}

async function stopFeed() {
    const feed = document.getElementById('video-feed');
    const placeholder = document.getElementById('feed-placeholder');
    const btn = document.getElementById('btn-start');
    const browserCam = document.getElementById('browser-cam');
    
    try {
        // Stop browser webcam if active
        if (isBrowserCamMode) {
            if (browserCamInterval) {
                clearInterval(browserCamInterval);
                browserCamInterval = null;
            }
            if (browserStream) {
                browserStream.getTracks().forEach(track => track.stop());
                browserStream = null;
            }
            if (browserCam) {
                browserCam.srcObject = null;
                browserCam.classList.add('hidden');
            }
            isBrowserCamMode = false;
        }
        
        // Stop server camera if it was active
        if (token && !isBrowserCamMode) {
            try { await apiRequest('/camera/stop', 'POST', null, false); } catch(e) {}
        }
        
        feed.src = "";
        feed.classList.add('hidden');
        placeholder.classList.remove('hidden');
        btn.textContent = "Start Node";
        btn.disabled = false;
        isLive = false;
    } catch (e) {
        showToast("Stop failed", "error");
    }
}

// ── ACTIONS ───────────────────────────────────────

function showToast(message, type = "info") {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

// ── LISTENERS ────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    if (token) showApp();

    document.getElementById('login-form').onsubmit = (e) => {
        e.preventDefault();
        login(document.getElementById('login-user').value, document.getElementById('login-pass').value);
    };

    document.getElementById('signup-form').onsubmit = (e) => {
        e.preventDefault();
        signup(
            document.getElementById('signup-user').value, 
            document.getElementById('signup-email').value, 
            document.getElementById('signup-pass').value
        );
    };

    document.getElementById('show-signup').onclick = (e) => {
        e.preventDefault();
        switchOverlay('signup-overlay');
    };

    document.getElementById('show-login').onclick = (e) => {
        e.preventDefault();
        switchOverlay('auth-overlay');
    };

    document.getElementById('btn-logout').onclick = (e) => {
        e.preventDefault();
        logout();
    };

    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.onclick = (e) => {
            e.preventDefault();
            switchView(btn.dataset.view);
        };
    });

    document.getElementById('btn-start').onclick = startFeed;
    document.getElementById('btn-stop').onclick = stopFeed;

    // Upload interaction
    const zone = document.getElementById('upload-zone');
    const input = document.getElementById('file-input');
    
    zone.onclick = () => input.click();
    input.onchange = (e) => handleUpload(e.target.files[0]);
    
    zone.ondragover = (e) => { e.preventDefault(); zone.classList.add('dragover'); };
    zone.ondragleave = () => zone.classList.remove('dragover');
    zone.ondrop = (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        handleUpload(e.dataTransfer.files[0]);
    };

    // Dispatch buttons logic
    document.querySelectorAll('.dispatch-btn').forEach(btn => {
        btn.onclick = () => {
            const service = btn.dataset.service;
            fetch(`/dispatch/${service}`)
                .then(() => showToast(`AI Dispatch triggered for ${service.toUpperCase()}`, "success"))
                .catch(() => showToast("Failed to trigger AI Agent", "error"));
        };
    });

    document.getElementById('btn-save-email').onclick = () => {
        const email = document.getElementById('alert-email').value;
        apiRequest(`/settings/alert-recipient?email=${email}`, 'POST', null, true)
            .then(() => showToast("Alert recipient updated", "success"))
            .catch(() => showToast("Failed to update recipient", "error"));
    };

    // New functional listeners
    document.getElementById('btn-refresh-stats').onclick = () => {
        updateStatus();
        updateEvents();
        showToast("System data synchronized", "info");
    };

    document.getElementById('filter-type').onchange = () => {
        updateEvents();
    };
});
