"""
AlertX — Global Configuration
Centralizes all tunable parameters, paths, and thresholds.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LEARNING_LOG = os.path.join(LOG_DIR, "learning_log.jsonl")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ──────────────────────────────────────────────
# Camera / Stream
# ──────────────────────────────────────────────
# Change to your IP camera URL or use 0 for local webcam
CAMERA_SOURCE = os.getenv("ALERTX_CAMERA", "0")
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FPS_LIMIT = 15  # max frames per second to process

# ──────────────────────────────────────────────
# YOLO Model
# ──────────────────────────────────────────────
YOLO_MODEL = os.getenv("ALERTX_YOLO_MODEL", "yolov8n.pt")  # Use Nano model for free cloud tier CPU
YOLO_CONF_THRESHOLD = 0.55  # INCREASED: Be much more certain before detecting
YOLO_IOU_THRESHOLD = 0.45
WEAPON_CONF_THRESHOLD = 0.65 # Stricter for weapons

# ──────────────────────────────────────────────
# Detection — class-to-incident mapping
# Maps COCO class names → AlertX incident types
# ──────────────────────────────────────────────
INCIDENT_CLASS_MAP = {
    "fire": "fire",
    "smoke": "fire",
    "knife": "weapon",
    "scissors": "weapon",
    "baseball bat": "weapon",
    "car": "vehicle",       # Internal label, logic will filter for "accident"
    "truck": "vehicle",
    "bus": "vehicle",
    "motorcycle": "vehicle",
    "person": "person",
}

# How many persons in single frame = crowd alert
CROWD_THRESHOLD = 20

# ──────────────────────────────────────────────
# Threat Severity — score thresholds
# ──────────────────────────────────────────────
SEVERITY_THRESHOLDS = {
    "LOW": 0.25,
    "MEDIUM": 0.50,
    "HIGH": 0.75,
    "CRITICAL": 0.90,
}

# ──────────────────────────────────────────────
# Alert cooldown (seconds) — prevents duplicate alerts
# ──────────────────────────────────────────────
ALERT_COOLDOWN = 15

# ──────────────────────────────────────────────
# Event store
# ──────────────────────────────────────────────
MAX_EVENTS = 500  # keep last N events in memory

# ──────────────────────────────────────────────
# Email Alerts (SMTP)
# ──────────────────────────────────────────────
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")   # e.g. your-email@gmail.com
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")   # your app password
MAIL_RECIPIENT = os.getenv("MAIL_RECIPIENT", "") # where to send alerts

# ── Voice AI Dispatch (Vapi) ────────────────────
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "") # Your AI Agent ID
VAPI_PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID", "") # Your Vapi Number ID
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000") # For callback/webhook
DISPATCH_PHONE_NUMBER = os.getenv("DISPATCH_PHONE_NUMBER", "") # Your phone number
# ──────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 8000))
