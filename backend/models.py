import os
import re
import urllib.parse
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# Database setup
# DYNAMIC: Use Supabase if DATABASE_URL is set, otherwise use local SQLite
raw_url = os.getenv("DATABASE_URL", "sqlite:///./alertx.db").strip()

def create_safe_engine(url):
    try:
        # 1. Clean the URL
        if "postgres://" in url:
            url = url.replace("postgres://", "postgresql://", 1)
        
        # 2. Check for [YOUR-PASSWORD]
        if "[YOUR-PASSWORD]" in url:
            raise ValueError("Password not set")

        # 3. Handle special characters in password automatically
        # We find the part between :// and @
        if "@" in url and "://" in url:
            prefix, rest = url.split("://", 1)
            auth, host = rest.rsplit("@", 1)
            if ":" in auth:
                user, password = auth.split(":", 1)
                # Safely encode the password
                safe_pass = urllib.parse.quote_plus(password)
                url = f"{prefix}://{user}:{safe_pass}@{host}"

        # 4. Try to create and connect
        temp_engine = create_engine(
            url,
            connect_args={"check_same_thread": False} if "sqlite" in url else {
                "sslmode": "require",
                "connect_timeout": 10
            }
        )
        # Test connection
        with temp_engine.connect() as conn:
            pass
        return temp_engine, url
    except Exception as e:
        print(f"⚠️ DATABASE ERROR: {e}")
        print("🔄 FALLING BACK TO LOCAL SQLITE MODE...")
        fallback_url = "sqlite:///./alertx.db"
        return create_engine(fallback_url, connect_args={"check_same_thread": False}), fallback_url

engine, SQLALCHEMY_DATABASE_URL = create_safe_engine(raw_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    incident_type = Column(String, index=True)
    confidence = Column(Float)
    priority = Column(String)
    source = Column(String)
    description = Column(String)
    screenshot_path = Column(String, nullable=True)

# Create tables
try:
    Base.metadata.create_all(bind=engine)
except Exception as ddl_err:
    print(f"⚠️ TABLE CREATION ERROR: {ddl_err}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
