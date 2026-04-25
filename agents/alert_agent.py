"""
AlertX — Alert Agent
Dispatches alerts to the event store and console.
Includes cooldown logic to prevent duplicate consecutive alerts.
"""

import time
from typing import Any, Dict

from agents.base_agent import BaseAgent
from backend.config import ALERT_COOLDOWN
from backend.event_store import Event, EventStore
from utils.email_service import send_email_alert
from utils.image_host import upload_frame
# Import for updating global context
import backend.main as main_module


class AlertAgent(BaseAgent):
    """
    For each incident that passes the cooldown window,
    creates an Event and pushes it to the EventStore.
    """

    def __init__(self):
        super().__init__("alert")
        self._store = EventStore()
        self._last_alert_time: Dict[str, float] = {}  # incident_type → timestamp

    def _should_alert(self, incident_type: str) -> bool:
        now = time.time()
        last = self._last_alert_time.get(incident_type, 0)
        if now - last >= ALERT_COOLDOWN:
            self._last_alert_time[incident_type] = now
            return True
        return False

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        incidents = data.get("incidents", [])
        source = data.get("source", "live")
        frame_index = data.get("frame_index", 0)
        alerts_dispatched = []

        # ── Grouping ──────────────────────────────────
        # Only process the highest confidence incident of each type per frame
        unique_incidents = {}
        for inc in incidents:
            itype = inc["type"]
            if itype not in unique_incidents or inc["confidence"] > unique_incidents[itype]["confidence"]:
                unique_incidents[itype] = inc

        for itype, inc in unique_incidents.items():
            if not self._should_alert(itype):
                continue

            event = Event(
                incident_type=itype,
                severity=inc.get("severity_label", "LOW"),
                priority=inc.get("priority", "LOW"),
                confidence=inc["confidence"],
                details=inc.get("summary", ""),
                source=source,
                frame_index=frame_index,
            )
            self._store.add_event(event)
            alerts_dispatched.append(event.to_dict())

            # Console alert with fallback for missing priority
            prio = inc.get("priority", "LOW")
            icon = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "🔔", "LOW": "ℹ️"}.get(prio, "📋")
            msg = f"{icon} [{prio}] {inc.get('summary', 'Unknown Event')}"
            self.logger.warning(msg)

            if inc["priority"] in ["HIGH", "CRITICAL"]:
                # Get the evidence frame
                evidence_frame = None
                media_url = None
                frame_result = data.get("frame_result")
                
                if frame_result and frame_result.annotated_frame is not None:
                    evidence_frame = frame_result.annotated_frame
                    # Still upload a link as a secondary fallback
                    media_url = upload_frame(evidence_frame)
                
                # Build rich email body
                subject = f"{inc['priority']} Incident: {inc['type'].upper()}"
                body = f"AlertX detected a {inc['priority']} priority event.\n\n"
                body += f"Type: {inc['type'].upper()}\n"
                body += f"Summary: {inc['summary']}\n"
                body += f"Time: {inc.get('timestamp', 'N/A')}\n"
                if media_url:
                    body += f"\nWeb link: {media_url}\n"
                
                # Update global context for AI dispatch
                main_module._last_high_priority_event = inc["summary"]
                
                # Dispatch email with dynamic recipient override
                recipient = data.get("recipient_override")
                send_email_alert(subject, body, frame=evidence_frame, recipient=recipient)

        data["alerts_dispatched"] = alerts_dispatched
        self._processed_count += 1
        return data
