import base64
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("alertx.email")

def send_email(subject, message, image_data=None):
    """Sends an email using the official Gmail REST API (Bypasses SMTP blocks)."""
    
    # ── CREDENTIALS ─────────────────────────────────
    # These must be set in Hugging Face Secrets
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
    recipient_email = os.getenv("MAIL_RECIPIENT")
    
    if not all([client_id, client_secret, refresh_token, recipient_email]):
        logger.error("Email Error: Missing Gmail API Secrets! (CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, or RECIPIENT)")
        return False

    try:
        # 1. Authenticate via OAuth2
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token"
        )
        
        service = build('gmail', 'v1', credentials=creds, cache_discovery=False)

        # 2. Construct the Email
        msg = MIMEMultipart()
        msg['To'] = recipient_email
        msg['Subject'] = f"AlertX Security: {subject}"

        # Attach HTML text
        msg.attach(MIMEText(message, 'html'))

        # Attach image if provided
        if image_data:
            try:
                img = MIMEImage(image_data)
                img.add_header('Content-Disposition', 'attachment', filename="incident.jpg")
                msg.attach(img)
            except Exception as ie:
                logger.error(f"Image Attachment Error: {ie}")

        # 3. Encode the message for the Gmail API
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        body = {'raw': raw_message}

        # 4. Send via HTTP
        logger.info("Sending email via Gmail REST API...")
        sent_message = service.users().messages().send(userId="me", body=body).execute()
        
        logger.info(f"✅ Email Alert sent successfully! Message ID: {sent_message.get('id')}")
        return True

    except HttpError as error:
        logger.error(f"❌ Gmail API Error: {error}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected Error during email dispatch: {e}")
        return False
