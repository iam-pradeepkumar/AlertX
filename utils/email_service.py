import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

logger = logging.getLogger("alertx.email")

def send_email(subject, message, image_data=None):
    """Sends an email using Gmail App Password (SMTP)."""
    # ── SETTINGS ─────────────────────────────────
    smtp_server = "smtp.gmail.com"
    smtp_port = 465 # SSL Mode
    
    # These must be set in your Secrets/Env
    sender_email = os.getenv("MAIL_USERNAME")
    app_password = os.getenv("MAIL_PASSWORD") # This is your 16-character App Password
    recipient_email = os.getenv("MAIL_RECIPIENT") # Fixed recipient
    
    if not sender_email or not app_password or not recipient_email:
        logger.error("Email Error: MAIL_USERNAME, MAIL_PASSWORD, or MAIL_RECIPIENT missing!")
        return False

    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = f"AlertX Security: {subject}"

        # Attach text
        msg.attach(MIMEText(message, 'plain'))

        # Attach image if provided
        if image_data:
            try:
                img = MIMEImage(image_data)
                img.add_header('Content-Disposition', 'attachment', filename="incident.jpg")
                msg.attach(img)
            except Exception as ie:
                logger.error(f"Image Attachment Error: {ie}")

        # Send with a strict timeout to prevent hanging on cloud providers
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=5) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)
            
        logger.info(f"✅ Email Alert sent successfully to {recipient_email}")
        return True

    except Exception as e:
        logger.error(f"❌ SMTP SSL Error: {e}")
        # Fallback to Port 587 if 465 fails
        try:
            logger.info("Retrying with Port 587 (TLS)...")
            with smtplib.SMTP(smtp_server, 587, timeout=5) as server:
                server.starttls()
                server.login(sender_email, app_password)
                server.send_message(msg)
            logger.info(f"✅ Email Alert sent via TLS to {recipient_email}")
            return True
        except Exception as e2:
            logger.error(f"❌ All SMTP attempts failed: {e2}")
            return False
