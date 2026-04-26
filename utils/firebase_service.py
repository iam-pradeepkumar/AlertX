import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger("alertx.firebase")

# Global variables for the app and db
_db = None

def init_firebase():
    """Initializes Firebase using the Service Account JSON from env vars."""
    global _db
    try:
        if not firebase_admin._apps:
            service_account_info = os.getenv("FIREBASE_SERVICE_ACCOUNT")
            if not service_account_info:
                logger.warning("❌ FIREBASE_SERVICE_ACCOUNT secret not found! Falling back to Local Mode.")
                return None
            
            # Parse the JSON string
            cred_dict = json.loads(service_account_info)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            logger.info("✅ Firebase Cloud initialized successfully!")
        
        _db = firestore.client()
        return _db
    except Exception as e:
        logger.error(f"❌ Firebase Initialization Failed: {e}")
        return None

def get_firestore():
    """Returns the Firestore client, initializing if necessary."""
    global _db
    if _db is None:
        return init_firebase()
    return _db
