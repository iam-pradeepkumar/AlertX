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
            cred = None
            
            # 1. Try environment variable (JSON string)
            env_cred = os.getenv("FIREBASE_SERVICE_ACCOUNT")
            if env_cred:
                import json
                try:
                    cred_dict = json.loads(env_cred)
                    cred = credentials.Certificate(cred_dict)
                    logger.info("Firebase initialized via FIREBASE_SERVICE_ACCOUNT env var")
                except Exception as e:
                    logger.error(f"Failed to parse FIREBASE_SERVICE_ACCOUNT env var: {e}")

            # 2. Try serviceAccountKey.json
            if not cred:
                cred_path = os.path.join(os.getcwd(), "serviceAccountKey.json")
                if os.path.exists(cred_path):
                    cred = credentials.Certificate(cred_path)
                    logger.info("Firebase initialized with serviceAccountKey.json")

            # 3. Try credentials.json (Legacy/Common name)
            if not cred:
                legacy_path = os.path.join(os.getcwd(), "credentials.json")
                if os.path.exists(legacy_path):
                    cred = credentials.Certificate(legacy_path)
                    logger.info("Firebase initialized with credentials.json")

            # Initialize with cred or default
            if cred:
                firebase_admin.initialize_app(cred)
            else:
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
