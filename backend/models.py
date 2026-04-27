import os
import sqlite3
from datetime import datetime
import uuid
import logging

logger = logging.getLogger("alertx.db")

# SQLite Database Path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alertx.db")

def init_db():
    """Initialize SQLite database and create tables."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create Users Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                email TEXT,
                hashed_password TEXT,
                role TEXT,
                badge_id TEXT,
                created_at TEXT
            )
        ''')
        
        # Create Events Table (for persistence)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                incident_type TEXT,
                severity TEXT,
                priority TEXT,
                confidence REAL,
                details TEXT,
                source TEXT,
                timestamp TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"SQLite Database initialized at {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

# Initialize on import
init_db()

class DBStore:
    """Helper to handle SQLite Storage."""
    @staticmethod
    def save_event(data: dict):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            event_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO events (id, incident_type, severity, priority, confidence, details, source, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event_id,
                data.get("incident_type"),
                data.get("severity"),
                data.get("priority"),
                data.get("confidence"),
                data.get("details"),
                data.get("source", "live"),
                datetime.utcnow().isoformat()
            ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving event: {e}")
            return False

    @staticmethod
    def get_events(limit=50):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM events ORDER BY timestamp DESC LIMIT ?', (limit,))
            rows = cursor.fetchall()
            events = [dict(row) for row in rows]
            conn.close()
            return events
        except Exception as e:
            logger.error(f"Error fetching events: {e}")
            return []

    @staticmethod
    def save_user(username, email, hashed_password, role="civilian", badge_id=""):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (username, email, hashed_password, role, badge_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, email, hashed_password, role, badge_id, datetime.utcnow().isoformat()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving user: {e}")
            return False

    @staticmethod
    def get_user(username):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching user: {e}")
            return None

# Compatibility classes for main.py
class User:
    """Mock class for Auth compatibility."""
    pass

class Event:
    """Mock class for DB compatibility."""
    pass

# Compatibility constants for main.py
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

def get_db():
    """Returns the SQLite store."""
    return DBStore()
