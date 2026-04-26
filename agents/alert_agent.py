"""
AlertX — Alert Agent
Dispatches alerts to the event store and console.
Includes cooldown logic to prevent duplicate consecutive alerts.
"""

import time
import cv2
from datetime import datetime
from typing import Any, Dict

from agents.base_agent import BaseAgent
from backend.config import ALERT_COOLDOWN
from backend.event_store import Event, EventStore
from utils.email_service import send_email
from utils.image_host import upload_frame
# Import for updating global context
import backend.main as main_module


class AlertAgent(BaseAgent):
    """
    AlertAgent — Dispatches notifications to Email.
    Includes smart de-duplication for uploaded files.
    """

    def __init__(self):
        super().__init__("alert")
        self._store = EventStore()
        self._last_alert_time: Dict[str, float] = {}  # incident_type → timestamp
        self._alerted_files = set() # Track already alerted files

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
                
                # ── DISPATCH ────────────────────────────
                # Deduplication Logic
                # ── ALIGNMENT & DEDUPLICATION ────────────────
                source_name = data.get("source", "live")
                incident_type = itype.upper()
                priority = prio.upper()
                
                can_alert = False
                if source_name == "live":
                    elapsed = time.time() - self._last_alert_time.get(incident_type, 0)
                    if elapsed >= ALERT_COOLDOWN:
                        can_alert = True
                    else:
                        logger.info(f"⏳ Cooldown: {incident_type} alert squelched ({int(ALERT_COOLDOWN - elapsed)}s left)")
                else:
                    if source_name not in self._alerted_files:
                        can_alert = True
                    else:
                        logger.info(f"⏭️ Deduplication: File '{source_name}' already notified.")

                if not can_alert:
                    continue

                # ── PREPARE MEDIA ──────────────────────────
                image_bytes = None
                if frame_result.annotated_frame is not None:
                    try:
                        _, buffer = cv2.imencode('.jpg', frame_result.annotated_frame)
                        image_bytes = buffer.tobytes()
                    except Exception as ie:
                        logger.error(f"Image Encoding Error: {ie}")

                # ── DISPATCH ──────────────────────────────
                alert_msg = f"--- ALERTX SECURITY ALERT ---\n\n"
                alert_msg += f"Incident: {incident_type}\n"
                alert_msg += f"Priority: {priority}\n"
                alert_msg += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                alert_msg += f"Source: {source_name}\n"
                summary = data.get("high_priority_summary") or inc.get("summary", "No details")
                alert_msg += f"Summary: {summary}\n"
                alert_msg += "\n-----------------------------\n"
                alert_msg += "View live at: " + main_module.PUBLIC_URL + "\n"

                logger.info(f"📧 Sending Email Alert for {incident_type}...")
                success = send_email(
                    subject=f"🚨 {priority} ALERT: {incident_type}",
                    message=alert_msg,
                    image_data=image_bytes
                )

                if success:
                    alerts_dispatched += 1
                    if source_name == "live":
                        self._last_alert_time[incident_type] = time.time()
                    else:
                        self._alerted_files.add(source_name)
                    
                    # Update global context for Voice AI
                    main_module._last_high_priority_event = summary

        data["alerts_dispatched"] = alerts_dispatched
        self._processed_count += 1
        return data
