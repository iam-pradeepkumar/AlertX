import requests
import logging
import cv2
import os

logger = logging.getLogger("alertx.discord")

def send_discord_alert(subject, body, frame=None):
    """
    Sends a rich alert to Discord via Webhook.
    Works perfectly on Hugging Face because it uses HTTP (Port 443).
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return False

    try:
        # Prepare the payload
        payload = {
            "content": f"🚨 **{subject}**",
            "embeds": [{
                "title": "AlertX Security Incident",
                "description": body,
                "color": 15548997 if "CRITICAL" in subject else 15105570
            }]
        }

        # If we have a frame, we need to send it as a file
        if frame is not None:
            _, buffer = cv2.imencode('.jpg', frame)
            files = {'file': ('incident.jpg', buffer.tobytes(), 'image/jpeg')}
            response = requests.post(webhook_url, data={"payload_json": requests.utils.quote(str(payload))}, files=files)
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
