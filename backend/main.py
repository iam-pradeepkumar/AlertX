"""
AlertX — FastAPI Backend
Serves live video feed, upload/analysis endpoints, and event API.
"""

import asyncio
import base64
import logging
import os
import time
import threading
import uuid
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict
from io import BytesIO

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Depends, Response
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.auth import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    get_current_user
)
from backend.models import get_db, User
from backend.config import (
    BASE_DIR,
    UPLOAD_DIR,
    HOST,
    PORT,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    FPS_LIMIT,
    PUBLIC_URL,
    DISPATCH_PHONE_NUMBER,
)
from backend.event_store import EventStore
from pipeline.frame_grabber import FrameGrabber
from utils.vapi_service import trigger_ai_dispatch
from pipeline.detector import YOLODetector
from agents.detection_agent import DetectionAgent
from agents.threat_agent import ThreatAnalysisAgent
from agents.decision_agent import DecisionAgent
from agents.alert_agent import AlertAgent
from agents.learning_agent import LearningAgent

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-28s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("alertx.server")

# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────
app = FastAPI(
    title="AlertX — AI Surveillance Platform",
    version="1.0.0",
    description="Real-time incident detection from live CCTV and uploaded video.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve upload files for playback
if os.path.isdir(UPLOAD_DIR):
    app.mount("/media", StaticFiles(directory=UPLOAD_DIR), name="media")

# ──────────────────────────────────────────────
# Singletons
# ──────────────────────────────────────────────
event_store = EventStore()
detector = YOLODetector()
frame_grabber: Optional[FrameGrabber] = None

# Agent pipeline
detection_agent = DetectionAgent()
threat_agent = ThreatAnalysisAgent()
decision_agent = DecisionAgent()
alert_agent = AlertAgent()
learning_agent = LearningAgent()

_processing_live = False
_live_thread: Optional[threading.Thread] = None
_latest_annotated_frame: Optional[np.ndarray] = None
_last_frame_id = -1
_latest_encoded_frame = None
_last_encoded_frame_id = -1

# Optimization helpers
agent_executor = ThreadPoolExecutor(max_workers=3)
_is_processing_incident = False # Busy lock to prevent lag during heavy analysis
_last_high_priority_event = None # Store context for Voice AI
_stream_tickets: Dict[str, float] = {}
_last_activity_time = 0.0 # Track any camera activity (server or browser)

@app.on_event("startup")
async def startup_event():
    """Pre-load YOLO model on startup."""
    print("🚀 Pre-loading YOLO model...")
    detector.load()
    print("✅ Model ready.")
_alert_recipient = ""
_last_high_priority_event = "No recent incident recorded."

# Load persistent recipient if exists
if os.path.exists(".recipient"):
    try:
        with open(".recipient", "r") as f:
            _alert_recipient = f.read().strip()
    except:
        pass
# Fallback to env
if not _alert_recipient:
    _alert_recipient = os.getenv("MAIL_RECIPIENT", "")


@app.get("/dispatch/{service}")
async def dispatch_service(service: str):
    """Trigger AI Voice call to your personal number regarding a service."""
    # Use your personal number for all alerts if set
    target_number = DISPATCH_PHONE_NUMBER
    
    if not target_number:
        return HTMLResponse(content="""
            <html>
                <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background: #0a0a0f; color: white;">
                    <h1 style="color: #ef4444;">❌ No Phone Number Set</h1>
                    <p>Please add DISPATCH_PHONE_NUMBER to your .env file.</p>
                </body>
            </html>
        """)

    success = trigger_ai_dispatch(
        service=service.upper(),
        incident_details=_last_high_priority_event,
        destination_number=target_number
    )
    
    return HTMLResponse(content=f"""
        <html>
            <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background: #0a0a0f; color: white;">
                <h1 style="color: #4ade80;">✅ Dispatch Triggered!</h1>
                <p>AI Voice Agent is calling the {service.upper()} now.</p>
                <p style="color: #8b8ba3; font-size: 0.8rem;">Incident: {_last_high_priority_event}</p>
                <button onclick="window.close()" style="padding: 10px 20px; border-radius: 5px; cursor: pointer;">Close Window</button>
            </body>
        </html>
    """)


# ── Autonomous Dispatch ──────────────────────
class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

@app.post("/auth/signup")
async def signup(request: SignupRequest, db: Session = Depends(get_db)):
    """Create a new user account."""
    # Check if user exists
    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    new_user = User(
        username=request.username,
        email=request.email,
        hashed_password=get_password_hash(request.password)
    )
    db.add(new_user)
    db.commit()
    return {"status": "success", "message": "User created successfully"}

@app.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Verify user and return JWT token."""
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me")
async def read_users_me(current_user: str = Depends(get_current_user)):
    return {"username": current_user}

@app.post("/auth/stream-token")
async def get_stream_token(current_user: str = Depends(get_current_user)):
    """Generate a high-security ticket for the video stream."""
    ticket = str(uuid.uuid4())
    # Store ticket with 60s expiry
    _stream_tickets[ticket] = time.time() + 60
    return {"ticket": ticket}
@app.post("/settings/alert-recipient")
async def update_alert_recipient(email: str = Query(...), current_user: str = Depends(get_current_user)):
    global _alert_recipient
    _alert_recipient = email
    # Persist to disk
    with open(".recipient", "w") as f:
        f.write(_alert_recipient)
    return {"status": "success", "recipient": _alert_recipient}


def _bg_agent_task(frame_result, source, frame_index, recipient):
    """Background task runner for the agent pipeline."""
    global _is_processing_incident, _last_high_priority_event
    try:
        _is_processing_incident = True
        data = {
            "frame_result": frame_result,
            "source": source,
            "frame_index": frame_index,
            "recipient_override": recipient
        }
        # Run full agent chain
        # Run full mission-critical agent chain
        data = detection_agent.process(data)
        data = threat_agent.process(data)
        data = decision_agent.process(data) # Restored: This sets the priority!
        data = alert_agent.process(data)
        data = learning_agent.process(data)
        
        # Save context for potential Voice AI dispatch
        if data.get("high_priority_summary"):
            _last_high_priority_event = data["high_priority_summary"]
            
    except Exception as e:
        logger.error(f"Background Agent Error: {e}")
    finally:
        _is_processing_incident = False

_last_pipeline_run = 0.0

def run_agent_pipeline(frame_result, source="live", frame_index=0):
    """Offloads the agent pipeline to a background thread to prevent camera lag."""
    global _is_processing_incident, _last_pipeline_run
    
    # PERFORMANCE: Only run the heavy agent pipeline every 2 seconds for a specific incident
    # This prevents the CPU from choking when detection is active
    if _is_processing_incident or (time.time() - _last_pipeline_run < 2.0):
        return
        
    _last_pipeline_run = time.time()
    global _alert_recipient
    # Submit to worker pool
    agent_executor.submit(_bg_agent_task, frame_result, source, frame_index, _alert_recipient)


# ──────────────────────────────────────────────
# Live processing loop
# ──────────────────────────────────────────────
# Global buffer for the latest annotated frame (to avoid lag in video_feed)
_latest_annotated_frame = None
_latest_encoded_frame = None  # Performance: Cache the JPEG to save CPU
_last_encoded_frame_id = -1

def _live_processing_loop():
    """Background thread that grabs frames, runs detection, and feeds agents."""
    global _processing_live, _latest_annotated_frame, _last_frame_id
    frame_idx = 0
    # Process at slightly lower frequency to keep CPU cool
    interval = 1.0 / 30.0 # max 30 fps capture

    while _processing_live and frame_grabber and frame_grabber.is_running:
        start_time = time.time()
        frame = frame_grabber.get_frame()
        if frame is None:
            time.sleep(0.01)
            continue

        # LAG FIX: Drastic skipping for Hugging Face Free Tier
        # We only detect every 10-20 frames to ensure zero backlog lag
        skip_factor = 20 if _is_processing_incident else 10
        
        if frame_idx % skip_factor == 0:
            try:
                # Optimized Detection
                result = detector.detect(frame)
                _latest_annotated_frame = result.annotated_frame
                _last_frame_id = frame_idx
                
                global _last_activity_time
                _last_activity_time = time.time()
                
                if result.incidents:
                    run_agent_pipeline(result, source="live", frame_index=frame_idx)
            except Exception as e:
                logger.error(f"Detection error: {e}")

        frame_idx += 1
        
        # Adaptive sleep: ensure we stay at roughly 30 FPS for the grabber
        elapsed = time.time() - start_time
        sleep_time = max(0, interval - elapsed)
        time.sleep(sleep_time)


# ══════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard page."""
    index_path = os.path.join(dashboard_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>AlertX — Dashboard not found</h1>")


# ── Video Feed ─────────────────────────────────
def _get_latest_frame():
    """Fetch and encode the latest annotated frame, with caching."""
    global _latest_annotated_frame, _latest_encoded_frame, _last_encoded_frame_id
    
    if _latest_annotated_frame is None:
        return None

    # Performance: Only re-encode if it's a NEW frame
    if _last_encoded_frame_id == _last_frame_id and _latest_encoded_frame is not None:
        return _latest_encoded_frame
        
    # Downscale and compress even more for cloud speed
    out = _latest_annotated_frame
    h, w = out.shape[:2]
    new_w = 400
    new_h = int(h * (400 / w))
    small_frame = cv2.resize(out, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
    _, buffer = cv2.imencode(".jpg", small_frame, [cv2.IMWRITE_JPEG_QUALITY, 20])
    
    _latest_encoded_frame = buffer.tobytes()
    _last_encoded_frame_id = _last_frame_id
    return _latest_encoded_frame

def _video_generator():
    """Generator for MJPEG stream with zero-latency frame skipping."""
    while True:
        if not _processing_live:
            break
            
        if frame_grabber and frame_grabber.is_running:
            frame_bytes = _get_latest_frame()
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
        
        # Performance: Lower wait time for higher FPS
        time.sleep(0.01)

@app.get("/video_feed")
async def video_feed(ticket: str = Query(...)):
    """Video streaming route. Uses high-security one-time tickets."""
    expiry = _stream_tickets.get(ticket)
    if not expiry or time.time() > expiry:
        # Clean up expired
        if ticket in _stream_tickets: del _stream_tickets[ticket]
        raise HTTPException(status_code=401, detail="Stream ticket invalid or expired")
    
    # Optional: Log the access
    logger.info(f"Stream access authorized via ticket {ticket[:8]}...")
    
    return StreamingResponse(
        _video_generator(), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ── Camera Control ─────────────────────────────
@app.post("/camera/start")
async def start_camera(source: str = Query(default="0"), current_user: str = Depends(get_current_user)):
    """Start the live camera feed and processing."""
    global frame_grabber, _processing_live, _live_thread

    if frame_grabber and frame_grabber.is_running:
        return {"status": "already_running"}

    # Load model if needed
    if not detector.is_loaded:
        detector.load()

    frame_grabber = FrameGrabber(source=source)
    success = frame_grabber.start()
    if not success:
        # Returning 404 instead of 500 to signal "no camera" cleanly to the frontend
        raise HTTPException(status_code=404, detail=f"Camera source unavailable: {source}")

    # Start processing thread
    _processing_live = True
    _live_thread = threading.Thread(target=_live_processing_loop, daemon=True)
    _live_thread.start()

    logger.info(f"Camera started — source={source}")
    return {"status": "started", "source": source}


@app.post("/camera/stop")
async def stop_camera(current_user: str = Depends(get_current_user)):
    """Stop the live camera feed."""
    global frame_grabber, _processing_live

    _processing_live = False
    if frame_grabber:
        frame_grabber.stop()
        frame_grabber = None
    return {"status": "stopped"}


# ── Upload ─────────────────────────────────────
@app.post("/upload")
async def upload_video(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    """Upload a video file for later analysis."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    filename = f"{uuid.uuid4()}_{file.filename}"
    save_path = os.path.join(UPLOAD_DIR, filename)
    
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    
    size_mb = round(len(content) / (1024 * 1024), 2)
    logger.info(f"Uploaded: {filename} ({size_mb} MB)")
    return {
        "status": "uploaded",
        "filename": filename,
        "size_mb": size_mb
    }


@app.post("/process_frame")
async def process_frame(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    """Process a single frame sent from the browser webcam (Cloud Mode)."""
    global _latest_annotated_frame, _last_frame_id, _last_activity_time
    
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        return {"status": "error", "message": "Invalid image"}
        
    # Update activity time for multi-device sync
    _last_activity_time = time.time()

    if not detector._loaded:
        detector.load()
        
    result = detector.detect(frame)
    _latest_annotated_frame = result.annotated_frame
    
    # Trigger agents if incidents found
    if result.incidents:
        run_agent_pipeline(result, source="browser_cam")

    # Encode result to send back to browser
    _, buffer = cv2.imencode('.jpg', result.annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
    img_str = base64.b64encode(buffer).decode()
    
    return {
        "status": "success",
        "frame": img_str,
        "incidents": result.incidents
    }


# ── Analyze ────────────────────────────────────
@app.post("/analyze")
def analyze_video(filename: str = Query(...), current_user: str = Depends(get_current_user)):
    """Analyze an uploaded video file and return a SINGLE consolidated summary."""
    video_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    if not detector.is_loaded:
        detector.load()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(status_code=500, detail="Cannot open video file")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    # Process ~1 frame per second of video for speed
    sample_interval = max(int(fps), 1)

    frame_idx = 0
    analysed_count = 0
    # Create gallery dir
    gallery_dir = os.path.join(UPLOAD_DIR, "gallery", filename)
    os.makedirs(gallery_dir, exist_ok=True)

    # Consolidated stats
    summary = {
        "incident_counts": {},   # type -> times detected
        "object_counts": {},     # class -> max count seen in any frame
        "peak_crowd_size": 0,
        "max_confidence": {},    # type -> highest confidence
        "gallery_images": [],    # paths to key frames
    }

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_interval == 0:
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
            result = detector.detect(frame)
            analysed_count += 1

            # Update summary icons/counts
            if result.incidents:
                # Save a screenshot if it's a new or high-conf incident
                shot_name = f"inc_{frame_idx}.jpg"
                shot_path = os.path.join(gallery_dir, shot_name)
                if len(summary["gallery_images"]) < 12: # Limit gallery size
                    cv2.imwrite(shot_path, result.annotated_frame)
                    summary["gallery_images"].append(f"/media/gallery/{filename}/{shot_name}")

                for inc in result.incidents:
                    itype = inc["type"]
                    summary["incident_counts"][itype] = summary["incident_counts"].get(itype, 0) + 1
                    summary["max_confidence"][itype] = max(summary["max_confidence"].get(itype, 0), inc["confidence"])
                    
                    if itype == "crowd":
                        summary["peak_crowd_size"] = max(summary["peak_crowd_size"], inc.get("count", 0))

            # Update object counts
            for det in result.detections:
                summary["object_counts"][det.class_name] = max(summary["object_counts"].get(det.class_name, 0), 1)

            # Optional: Dispatched limited events to store
            if result.incidents:
                run_agent_pipeline(result, source=f"upload:{filename}", frame_index=frame_idx)

        frame_idx += 1

    cap.release()

    # Flatten max_confidence and counts for response
    return {
        "status": "complete",
        "filename": filename,
        "summary": summary,
        "total_frames": total_frames,
        "frames_analyzed": analysed_count,
    }


# ── Events API ─────────────────────────────────
@app.get("/events")
async def get_events(
    limit: int = Query(default=50, le=200),
    incident_type: Optional[str] = Query(default=None),
):
    """Get latest detected events."""
    events = event_store.get_events(limit=limit, incident_type=incident_type)
    return {"events": events, "count": len(events)}


@app.get("/events/stats")
async def get_stats():
    """Get aggregate event statistics."""
    return event_store.get_stats()


@app.post("/events/{event_id}/acknowledge")
async def acknowledge_event(event_id: str):
    """Mark an event as acknowledged."""
    success = event_store.acknowledge_event(event_id)
    if not success:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "acknowledged", "event_id": event_id}


# ── System Status ──────────────────────────────
@app.get("/status")
async def system_status():
    """Overall system health and component status."""
    # Active if server grabber is running OR browser is pushing frames (last 10s)
    is_active = (frame_grabber is not None and frame_grabber.is_running) or \
                (time.time() - _last_activity_time < 10.0)
                
    return {
        "status": "online",
        "camera_active": is_active,
        "model_loaded": detector.is_loaded,
        "agents": {
            "detection": detection_agent.stats,
            "threat_analysis": threat_agent.stats,
            "decision": decision_agent.stats,
            "alert": alert_agent.stats,
            "learning": learning_agent.stats,
        },
        "events": event_store.get_stats(),
        "alert_recipient": _alert_recipient
    }




# ── Static Dashboard (Must be last) ────────────
dashboard_dir = os.path.join(BASE_DIR, "dashboard")
if os.path.isdir(dashboard_dir):
    app.mount("/", StaticFiles(directory=dashboard_dir, html=True), name="static_root")
