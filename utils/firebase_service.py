import os
import logging
import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger("alertx.firebase")

_db = None

def init_firebase():
    """Initialize Firebase Admin SDK."""
    global _db
    try:
        if not firebase_admin._apps:
            # Look for service account key in the root or env
            cred_path = os.path.join(os.getcwd(), "serviceAccountKey.json")
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase initialized with serviceAccountKey.json")
            else:
                # Fallback to default credentials (works in many cloud environments)
                firebase_admin.initialize_app()
                logger.info("Firebase initialized with default credentials")
        
        _db = firestore.client()
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        return False

def get_firestore():
    """Return the Firestore client."""
    global _db
    if _db is None:
        init_firebase()
    return _db
