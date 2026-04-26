import os
import re
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# Database setup
# DYNAMIC: Use Supabase if DATABASE_URL is set, otherwise use local SQLite
raw_url = os.getenv("DATABASE_URL", "sqlite:///./alertx.db").strip()

# SECURITY & FORMAT FIXES
if "postgres://" in raw_url:
    # SQLAlchemy requires postgresql://
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)

if "[YOUR-PASSWORD]" in raw_url:
    print("⚠️ WARNING: You forgot to replace [YOUR-PASSWORD] in your DATABASE_URL!")
    # Fallback to local to prevent crash
    SQLALCHEMY_DATABASE_URL = "sqlite:///./alertx.db"
else:
    SQLALCHEMY_DATABASE_URL = raw_url

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # Only use check_same_thread for SQLite
    connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {
        "sslmode": "require" # Recommended for Supabase
    }
)
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
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
