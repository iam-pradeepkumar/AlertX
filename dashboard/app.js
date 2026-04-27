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
// Google Auth removed. Using local authentication only.
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

function signup(username, email, password, role = "civilian", badge_id = "") {
    // Better compatibility: Send as JSON body
    apiRequest('/auth/signup', 'POST', { username, email, password, role, badge_id })
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
    
    showToast("Session terminated. Secure logout complete.", "info");
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

function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    const isOpen = sidebar.classList.contains('open');
    if (isOpen) {
        sidebar.classList.remove('open');
        backdrop.classList.remove('active');
    } else {
        sidebar.classList.add('open');
        backdrop.classList.add('active');
    }
}

function closeSidebar() {
    document.querySelector('.sidebar').classList.remove('open');
    document.getElementById('sidebar-backdrop').classList.remove('active');
}

function switchView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    
    const viewEl = document.getElementById(`view-${viewName}`);
    const navEl = document.querySelector(`[data-view="${viewName}"]`);
    
    if (viewEl) viewEl.classList.add('active');
    if (navEl) navEl.classList.add('active');
    
    // Close sidebar on mobile after navigating
    closeSidebar();
    
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
    
    // Live Clock for Geo-Intelligence Panel
    setInterval(() => {
        const timeEl = document.getElementById('live-sector-time');
        if (timeEl) {
            const now = new Date();
            timeEl.innerHTML = `LIVE: ${now.toLocaleDateString()} ${now.toLocaleTimeString()}`;
        }
    }, 1000);
    
    map = L.map('map').setView(userPos, 13);
    
    // Real Satellite View (Esri World Imagery)
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EBP, and the GIS User Community'
    }).addTo(map);

    // Overlay for labels (OpenStreetMap Hybrid)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        opacity: 0.5,
        className: 'map-labels-overlay'
    }).addTo(map);

    window.serviceMarkers = [];

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

async function findNearbyServices(pos, radius = 10000) {
    const container = document.getElementById('nearby-services');
    if (!container) return;
    
    container.innerHTML = `
        <div style="text-align:center; padding:2rem;">
            <span class="spinner-sm"></span>
            <p style="font-size:0.8rem; color:#8b8ba3; margin-top:10px;">Scanning sector (${radius/1000}km)...</p>
        </div>`;

    const lat = pos[0];
    const lon = pos[1];

    // Broaden search to include more emergency-related tags
    const query = `
        [out:json][timeout:30];
        (
          node["amenity"~"police|hospital|fire_station|ambulance_station|emergency_phone|doctor|pharmacy"](around:${radius},${lat},${lon});
          way["amenity"~"police|hospital|fire_station|ambulance_station"](around:${radius},${lat},${lon});
          node["emergency"~"yes|phone|defibrillator"](around:${radius},${lat},${lon});
        );
        out center body 20;
    `;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 35000); // 35s timeout

        const response = await fetch("https://overpass-api.de/api/interpreter", {
            method: "POST",
            body: query,
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);

        if (!response.ok) {
            if (response.status === 429) throw new Error("Server busy. Retrying...");
            throw new Error(`Overpass API Error: ${response.status}`);
        }

        const data = await response.json();
        
        if (!data.elements || data.elements.length === 0) {
            if (radius < 30000) {
                // Try broader search if nothing found
                console.log(`No units in ${radius}m, expanding search...`);
                return findNearbyServices(pos, radius + 10000);
            }
            container.innerHTML = `
                <div style="text-align:center; padding:1.5rem;">
                    <p style="color:#8b8ba3; font-size:0.8rem;">No verified units detected in this sector (30km scan).</p>
                    <button onclick="findNearbyServices([${lat}, ${lon}])" class="btn btn--ghost btn--sm" style="margin-top:10px;">Deep Scan</button>
                </div>`;
            return;
        }

        // Clear old markers
        if (window.serviceMarkers) {
            window.serviceMarkers.forEach(m => map.removeLayer(m));
            window.serviceMarkers = [];
        }

        const calcDist = (lat1, lon1, lat2, lon2) => {
            const R = 6371;
            const dLat = (lat2-lat1) * Math.PI / 180;
            const dLon = (lon2-lon1) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)*Math.sin(dLon/2);
            return R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a)));
        };

        const services = data.elements.map(el => {
            const elLat = el.lat || (el.center ? el.center.lat : null);
            const elLon = el.lon || (el.center ? el.center.lon : null);
            if (!elLat || !elLon) return null;

            const type = el.tags.amenity || el.tags.emergency || 'emergency';
            const name = el.tags.name || `Unit: ${type.replace(/_/g, ' ').toUpperCase()}`;
            
            let icon = '🛡️';
            if (type === 'police') icon = '🚓';
            if (type.includes('hospital') || type.includes('ambulance')) icon = '🏥';
            if (type === 'fire_station') icon = '🚒';
            if (type === 'doctor' || type === 'pharmacy') icon = '⚕️';

            const customIcon = L.divIcon({
                className: '',
                html: `<div style="font-size: 24px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));">${icon}</div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            });
            
            const marker = L.marker([elLat, elLon], { icon: customIcon }).addTo(map)
                .bindPopup(`<b>${icon} ${name}</b><br>${type.toUpperCase()}`);
            window.serviceMarkers.push(marker);

            return {
                name,
                type: type.replace(/_/g, ' '),
                dist: calcDist(lat, lon, elLat, elLon),
                icon
            };
        }).filter(s => s !== null);

        services.sort((a, b) => a.dist - b.dist);

        container.innerHTML = services.map(s => `
            <div class="service-card" style="display: flex; align-items: center; background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; margin-bottom: 8px; border: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 1.2rem; margin-right: 12px;">${s.icon}</div>
                <div>
                    <div style="font-size: 0.85rem; font-weight: 600;">${s.name}</div>
                    <div style="font-size: 0.7rem; color: #8b8ba3; text-transform: uppercase;">${s.type} • <span style="color:var(--online)">${s.dist.toFixed(1)}km</span></div>
                </div>
            </div>
        `).join('');

    } catch (e) {
        console.error("Geo-Intelligence Error:", e);
        container.innerHTML = `
            <div style="text-align:center; padding:1.5rem;">
                <p style="color:#ef4444; font-size:0.8rem;">Intelligence link disrupted.</p>
                <button onclick="findNearbyServices([${lat}, ${lon}])" class="btn btn--ghost btn--sm" style="margin-top:10px;">Retry Scan</button>
            </div>`;
    }
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
        
        const eventData = await apiRequest('/events?limit=100');
        const events = eventData.events || [];
        
        document.getElementById('stat-total').textContent = events.length;
        
        const critical = events.filter(e => e.priority === 'CRITICAL').length;
        const high = events.filter(e => e.priority === 'HIGH').length;
        document.getElementById('stat-critical').textContent = critical;
        const statHighEl = document.getElementById('stat-high');
        if (statHighEl) statHighEl.textContent = high;
        
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
        const filterVal = document.getElementById('filter-type').value;
        let url = `/events?limit=25`;
        
        if (filterVal) {
            const [prefix, value] = filterVal.split(':');
            if (prefix === 'p') url += `&priority=${value}`;
            else if (prefix === 't') url += `&incident_type=${value}`;
        }
        
        const data = await apiRequest(url);
        const events = data.events || [];
        
        const container = document.getElementById('event-list');
        const header = document.querySelector('.events-section h3');
        
        if (filterVal) {
            const [prefix, value] = filterVal.split(':');
            const label = value.toUpperCase();
            header.innerHTML = `Activity Log <span style="font-size: 0.65rem; color: var(--accent); background: var(--accent-glow); padding: 2px 6px; border-radius: 4px; margin-left: 8px;">Filter: ${label}</span>`;
        } else {
            header.innerHTML = `Activity Log`;
        }

        if (events.length === 0) {
            container.innerHTML = `<li style="padding: 2rem; text-align: center; color: var(--text-secondary);">No events found matching the current filter.</li>`;
            return;
        }

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
    if (source !== "") {
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
            feed.onload = () => { 
                btn.textContent = "Node Online"; 
                const badge = document.getElementById('node-status-badge');
                badge.textContent = "Online";
                badge.className = "badge badge--online";
            };
            showToast("Live Forensic Stream synchronized via Server Node", "success");
            return;
        } catch (e) {
            console.warn("AlertX: Server camera unavailable.", e.message);
            // Only fallback to browser webcam if the user is trying to use the default local cam (0)
            // If they provided a URL/Stream link, we should report the failure instead of switching to their face.
            if (source !== "0" && source !== "") {
                showToast(`Vision Link Failed: Source "${source}" unreachable.`, "error");
                stopFeed();
                return;
            }
        }
    }

    // ── STRATEGY 2: Browser webcam fallback (works on cloud) ──
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error("Browser does not support camera access");
        }

        console.log("AlertX: Server camera failed, initiating browser-side fallback...");
        showToast("Server has no camera. Switching to browser webcam...", "info");

        // PERF: Request lower resolution from phone camera to save memory/CPU
        browserStream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 480 }, height: { ideal: 360 }, facingMode: "environment" },
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

        // PERF: Use smaller canvas for AI detection (320x240 is plenty for YOLO)
        const DETECT_W = 320;
        const DETECT_H = 240;

        // Robust wait for video metadata
        if (browserCam.readyState >= 2) {
            canvas.width = DETECT_W;
            canvas.height = DETECT_H;
            overlay.width = browserCam.videoWidth;
            overlay.height = browserCam.videoHeight;
        } else {
            await new Promise((resolve) => {
                browserCam.onloadedmetadata = () => {
                    canvas.width = DETECT_W;
                    canvas.height = DETECT_H;
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

        // ── ADAPTIVE FRAME LOOP (replaces setInterval to prevent request overlap) ──
        // Uses setTimeout chaining: next frame only captured AFTER previous response returns.
        // This guarantees zero request pile-up on slow mobile networks.
        let adaptiveInterval = 1000; // Start at 1000ms (1 FPS) — safe for HF free-tier CPU
        const MIN_INTERVAL = 300;    // Fastest: ~3 FPS (fast WiFi + powerful server)
        const MAX_INTERVAL = 2500;   // Slowest: ~0.4 FPS (very slow mobile network)

        async function captureAndProcess() {
            if (!isLive || !isBrowserCamMode) return;

            const t0 = performance.now();
            try {
                // Capture frame at small detection resolution
                ctx.drawImage(browserCam, 0, 0, canvas.width, canvas.height);
                // PERF: Use 0.3 quality JPEG — much smaller payload over mobile networks
                const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.3));
                if (!blob) {
                    scheduleCaptureLoop();
                    return;
                }

                const formData = new FormData();
                formData.append('file', blob, 'frame.jpg');

                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 5000); // 5s hard timeout

                const response = await fetch(`${API_BASE}/process_frame`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData,
                    signal: controller.signal
                });
                clearTimeout(timeoutId);

                if (!response.ok) throw new Error('AI Sync Failed');
                const data = await response.json();

                // ── DRAW BOXES (Client Side) ──
                overlayCtx.clearRect(0, 0, overlay.width, overlay.height);
                
                // Scale factor between detection size and display size
                const scaleX = overlay.width / canvas.width;
                const scaleY = overlay.height / canvas.height;

                if (data.detections) {
                    data.detections.forEach(det => {
                        const [x1, y1, x2, y2] = det.box;
                        const color = det.type ? "#ff4d4d" : "#00ff88";
                        
                        overlayCtx.strokeStyle = color;
                        overlayCtx.lineWidth = 3;
                        overlayCtx.strokeRect(x1 * scaleX, y1 * scaleY, (x2-x1) * scaleX, (y2-y1) * scaleY);

                        overlayCtx.fillStyle = color;
                        overlayCtx.font = "bold 14px Outfit, sans-serif";
                        overlayCtx.fillText(`${det.label} ${Math.round(det.conf*100)}%`, x1 * scaleX, (y1 * scaleY) - 8);
                    });
                }

                if (data.incidents && data.incidents.length > 0) {
                    data.incidents.forEach(inc => showToast(`🚨 ${inc.type.toUpperCase()}!`, "error"));
                    updateEvents();
                }

                // ── ADAPTIVE SPEED: Adjust interval based on round-trip time ──
                const elapsed = performance.now() - t0;
                if (elapsed > 800) {
                    // Slow network — back off
                    adaptiveInterval = Math.min(adaptiveInterval + 200, MAX_INTERVAL);
                } else if (elapsed < 300) {
                    // Fast network — speed up
                    adaptiveInterval = Math.max(adaptiveInterval - 50, MIN_INTERVAL);
                }

            } catch (err) {
                if (err.name === 'AbortError') {
                    console.warn("AlertX: Frame request timed out, slowing down...");
                    adaptiveInterval = Math.min(adaptiveInterval + 300, MAX_INTERVAL);
                } else {
                    console.warn("AI Loop Error:", err);
                }
            }

            scheduleCaptureLoop();
        }

        function scheduleCaptureLoop() {
            if (!isLive || !isBrowserCamMode) return;
            browserCamInterval = setTimeout(captureAndProcess, adaptiveInterval);
        }

        // Start the loop after a brief delay for camera warm-up
        setTimeout(scheduleCaptureLoop, 1000);

        showToast("Intelligence Node Active — AI Vision Processing enabled", "success");
        const badge = document.getElementById('node-status-badge');
        badge.textContent = "Online (Cam)";
        badge.className = "badge badge--online";

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
                clearTimeout(browserCamInterval);  // Changed from clearInterval to clearTimeout
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

        const badge = document.getElementById('node-status-badge');
        badge.textContent = "Standby";
        badge.className = "badge badge--offline";
        showToast("Node Offline — Intelligence protocols suspended", "info");
    } catch (e) {
        showToast("Stop failed", "error");
    }
}

// ── ACTIONS ───────────────────────────────────────

function showToast(message, type = "info") {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px) scale(0.9)';
        toast.style.transition = 'all 0.4s ease';
        setTimeout(() => toast.remove(), 400);
    }, 4500);
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
            document.getElementById('signup-pass').value,
            document.getElementById('signup-role').value,
            document.getElementById('signup-badge').value
        );
    };

    const signupRole = document.getElementById('signup-role');
    if (signupRole) {
        signupRole.onchange = (e) => {
            const badgeGroup = document.getElementById('badge-group');
            if (e.target.value === 'official') badgeGroup.classList.remove('hidden');
            else badgeGroup.classList.add('hidden');
        };
    }

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

    // Hamburger menu (mobile)
    const hamburgerBtn = document.getElementById('hamburger-btn');
    const sidebarBackdrop = document.getElementById('sidebar-backdrop');
    if (hamburgerBtn) hamburgerBtn.onclick = toggleSidebar;
    if (sidebarBackdrop) sidebarBackdrop.onclick = closeSidebar;

    document.getElementById('btn-start').onclick = startFeed;
    document.getElementById('btn-stop').onclick = stopFeed;

    document.getElementById('btn-apply-source').onclick = () => {
        const source = document.getElementById('cam-source').value;
        showToast(`Vision source configured: ${source}`, "success");
        if (isLive) {
            showToast("Restart Node to apply new vision source", "info");
        }
    };

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
                .then(() => showToast(`AI Voice Agent contacted ${service.toUpperCase()}`, "success"))
                .catch(() => showToast("Emergency Protocol Error: AI Agent unreachable", "error"));
        };
    });

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
