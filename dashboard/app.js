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

    const response = await fetch(`${API_BASE}${endpoint}`, options);
    
    if (response.status === 401) {
        logout();
        throw new Error("Session expired. Please login again.");
    }
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Request failed");
    }
    
    return response.json();
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
    apiRequest(`/auth/signup?username=${username}&email=${email}&password=${password}`, 'POST')
        .then(() => {
            showToast("Account created. Please log in.", "success");
            switchOverlay('auth-overlay');
        })
        .catch(err => showToast(err.message, "error"));
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
        
        document.getElementById('stat-total').textContent = data.events ? data.events.total_events : 0;
        
        const eventData = await apiRequest('/events?limit=100');
        const events = eventData.events || [];
        
        const critical = events.filter(e => e.priority === 'CRITICAL').length;
        const high = events.filter(e => e.priority === 'HIGH').length;
        document.getElementById('stat-critical').textContent = critical;
        document.getElementById('stat-high').textContent = high;
        
        const statusMsg = document.getElementById('system-status-msg');
        if (statusMsg) statusMsg.textContent = data.camera_active ? "AI Node Online" : "AI Node Standby";
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
                    <div class="event-item__title">${e.details}</div>
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
                    <div class="event-item__title">${e.details}</div>
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
    try {
        const source = document.getElementById('cam-source').value || "0";
        console.log(`AlertX: Attempting to start camera with source: ${source}`);
        
        await apiRequest(`/camera/start?source=${encodeURIComponent(source)}`, 'POST', null, true);
        
        // Server camera worked — use MJPEG stream
        const authData = await apiRequest('/auth/stream-token', 'POST', null, true);
        const ticket = authData.ticket;
        
        feed.src = `/video_feed?ticket=${ticket}&t=${new Date().getTime()}`;
        feed.classList.remove('hidden');
        placeholder.classList.add('hidden');
        isLive = true;
        isBrowserCamMode = false;
        
        feed.onload = () => {
            btn.textContent = "Node Online";
        };
        
        showToast("Server camera connected", "success");
        return;
    } catch (e) {
        console.warn("Server camera unavailable, trying browser webcam...", e.message);
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
        browserCam.classList.remove('hidden');
        feed.classList.add('hidden');
        placeholder.classList.add('hidden');

        // Robust wait for video metadata
        if (browserCam.readyState >= 2) {
            console.log("AlertX: Browser camera metadata already available.");
            canvas.width = browserCam.videoWidth;
            canvas.height = browserCam.videoHeight;
        } else {
            console.log("AlertX: Waiting for browser camera metadata...");
            await new Promise((resolve) => {
                browserCam.onloadedmetadata = () => {
                    canvas.width = browserCam.videoWidth;
                    canvas.height = browserCam.videoHeight;
                    resolve();
                };
            });
        }

        await browserCam.play();
        console.log("AlertX: Browser camera playback started.");

        isLive = true;
        isBrowserCamMode = true;
        btn.textContent = "Browser Cam Live";
        btn.disabled = false;

        // Frame capture loop — send frames to server for YOLO processing
        let isProcessing = false;
        console.log("AlertX: Starting frame processing loop in 1s...");
        
        // Small delay to let the model settle on the server
        setTimeout(() => {
            browserCamInterval = setInterval(async () => {
            if (!isLive || !isBrowserCamMode || isProcessing) return;

            isProcessing = true;
            try {
                // Capture frame from video
                ctx.drawImage(browserCam, 0, 0, canvas.width, canvas.height);
                
                // Convert to JPEG blob
                const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.7));
                if (!blob) { isProcessing = false; return; }

                // Send to server for YOLO processing
                const formData = new FormData();
                formData.append('file', blob, 'frame.jpg');

                const processUrl = `${API_BASE}/process_frame`;
                const response = await fetch(processUrl, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });

                if (!response.ok) {
                    console.error('AlertX: Frame processing failed with status:', response.status);
                    throw new Error('Frame processing failed');
                }

                const data = await response.json();
                console.log("AlertX: Received processed frame, incidents:", data.incidents.length);

                // Display the annotated frame
                feed.src = `data:image/jpeg;base64,${data.frame}`;
                feed.classList.remove('hidden');
                browserCam.classList.add('hidden');

                // Show incident notifications
                if (data.incidents && data.incidents.length > 0) {
                    for (const inc of data.incidents) {
                        const conf = Math.round(inc.confidence * 100);
                        showToast(`🚨 ${inc.type.toUpperCase()} detected (${conf}%)`, "error");
                    }
                    updateEvents();
                }
            } finally {
                isProcessing = false;
            }
        }, 400); // ~2.5 FPS for stability
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
