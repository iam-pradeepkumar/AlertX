import os
from datetime import datetime
import uuid

# Local Storage (In-memory for simplicity, can be extended to SQLite)
_local_users = {}
_local_events = []

class DBStore:
    """Helper to handle Local Storage (replacing Firestore)."""
    @staticmethod
    def save_event(data: dict):
        event_id = str(uuid.uuid4())
        event = {
            "id": event_id,
            **data,
            "timestamp": datetime.utcnow()
        }
        _local_events.append(event)
        # Keep only last 500 events
        if len(_local_events) > 500:
            _local_events.pop(0)
        return True

    @staticmethod
    def get_events(limit=50):
        # Return last N events sorted by timestamp desc
        sorted_events = sorted(_local_events, key=lambda x: x['timestamp'], reverse=True)
        return sorted_events[:limit]

    @staticmethod
    def save_user(username, email, hashed_password, role="civilian", badge_id=""):
        _local_users[username] = {
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "role": role,
            "badge_id": badge_id,
            "created_at": datetime.utcnow()
        }
        return True

    @staticmethod
    def get_user(username):
        return _local_users.get(username)

# Compatibility classes for main.py
class User:
    """Mock class for Auth compatibility."""
    pass

class Event:
    """Mock class for DB compatibility."""
    pass

# Compatibility constants for main.py
SQLALCHEMY_DATABASE_URL = "local"

def get_db():
    """Returns the local store."""
    return DBStore()
