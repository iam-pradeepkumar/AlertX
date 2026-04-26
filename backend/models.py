import os
from datetime import datetime
from utils.firebase_service import get_firestore

# Firebase-based Models
class DBStore:
    """Helper to handle Firestore collections."""
    @staticmethod
    def save_event(data: dict):
        db = get_firestore()
        if db:
            db.collection("events").add({
                **data,
                "timestamp": datetime.utcnow()
            })
            return True
        return False

    @staticmethod
    def get_events(limit=50):
        db = get_firestore()
        if not db: return []
        docs = db.collection("events").order_by("timestamp", direction="DESCENDING").limit(limit).stream()
        return [{"id": d.id, **d.to_dict()} for d in docs]

    @staticmethod
    def save_user(username, email, hashed_password):
        db = get_firestore()
        if db:
            db.collection("users").document(username).set({
                "username": username,
                "email": email,
                "hashed_password": hashed_password,
                "created_at": datetime.utcnow()
            })
            return True
        return False

    @staticmethod
    def get_user(username):
        db = get_firestore()
        if not db: return None
        doc = db.collection("users").document(username).get()
        return doc.to_dict() if doc.exists else None

# Compatibility classes for main.py
class User:
    """Mock class for Auth compatibility."""
    pass

class Event:
    """Mock class for DB compatibility."""
    pass

# Compatibility constants for main.py
SQLALCHEMY_DATABASE_URL = "firebase"

def get_db():
    """Returns the Firestore store."""
    return DBStore()
