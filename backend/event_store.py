"""
AlertX — Event Store
Thread-safe in-memory store for detection events with deque-based rotation.
"""

import threading
import uuid
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional

from backend.config import MAX_EVENTS


class Event:
    """Single detection event."""

    def __init__(
        self,
        incident_type: str,
        severity: str,
        priority: str,
        confidence: float,
        details: str,
        source: str = "live",
        frame_index: int = 0,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.timestamp = datetime.now().isoformat()
        self.incident_type = incident_type
        self.severity = severity
        self.priority = priority
        self.confidence = round(confidence, 3)
        self.details = details
        self.source = source
        self.frame_index = frame_index
        self.acknowledged = False

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "incident_type": self.incident_type,
            "severity": self.severity,
            "priority": self.priority,
            "confidence": self.confidence,
            "details": self.details,
            "source": self.source,
            "frame_index": self.frame_index,
            "acknowledged": self.acknowledged,
        }


class EventStore:
    """Thread-safe ring-buffer for events."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._events: deque = deque(maxlen=MAX_EVENTS)
                    cls._instance._stats = {
                        "total_events": 0,
                        "by_type": {},
                        "by_priority": {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0},
                    }
        return cls._instance

    # ── Write ──────────────────────────────────
    def add_event(self, event: Event) -> None:
        with self._lock:
            self._events.appendleft(event)
            self._stats["total_events"] += 1
            itype = event.incident_type
            self._stats["by_type"][itype] = self._stats["by_type"].get(itype, 0) + 1
            self._stats["by_priority"][event.priority] = (
                self._stats["by_priority"].get(event.priority, 0) + 1
            )

    # ── Read ───────────────────────────────────
    def get_events(
        self, 
        limit: int = 50, 
        incident_type: Optional[str] = None,
        priority: Optional[str] = None
    ) -> List[Dict]:
        with self._lock:
            events = list(self._events)
        
        if incident_type:
            events = [e for e in events if e.incident_type == incident_type]
        if priority:
            events = [e for e in events if e.priority == priority]
            
        return [e.to_dict() for e in events[:limit]]

    def get_stats(self) -> Dict:
        with self._lock:
            return dict(self._stats)

    def acknowledge_event(self, event_id: str) -> bool:
        with self._lock:
            for event in self._events:
                if event.id == event_id:
                    event.acknowledged = True
                    return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
