import requests
import json
import logging
import cv2
import os
from datetime import datetime

logger = logging.getLogger("alertx.discord")

def send_discord_alert(subject, body, frame=None):
    """
    Sends a rich alert to Discord via Webhook.
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return False

    try:
        # Prepare the payload
        payload = {
            "embeds": [{
                "title": f"🚨 {subject}",
                "description": body,
                "color": 15548997 if "CRITICAL" in subject else 15105570,
                "timestamp": datetime.utcnow().isoformat()
            }]
        }

        # If we have a frame, we need to send it as a file
        if frame is not None:
            _, buffer = cv2.imencode('.jpg', frame)
            files = {'file': ('incident.jpg', buffer.tobytes(), 'image/jpeg')}
            # Discord requires payload_json when sending files
            response = requests.post(webhook_url, data={"payload_json": json.dumps(payload)}, files=files)
        else:
            response = requests.post(webhook_url, json=payload)

        if response.status_code < 300:
            logger.info("✅ Discord alert sent successfully!")
            return True
        else:
            logger.error(f"Discord error: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Failed to send Discord alert: {e}")
        return False
