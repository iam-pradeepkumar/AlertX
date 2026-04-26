import smtplib
import logging
import cv2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from backend.config import MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_RECIPIENT, PUBLIC_URL

logger = logging.getLogger("alertx.email")

def send_email_alert(subject: str, body: str, frame=None, recipient: str = None):
    """
    Sends an email alert using SMTP. 
    If a frame is provided, it is attached as an image.
    """
    target_email = recipient or MAIL_RECIPIENT
    
    if not MAIL_USERNAME or not MAIL_PASSWORD or not target_email:
        logger.warning(f"[STUB] Email Alert: {subject} - Credentials/Recipient missing.")
        return False

    try:
        msg = MIMEMultipart('related')
        msg['From'] = MAIL_USERNAME
        msg['To'] = target_email
        msg['Subject'] = f"🛡️ AlertX: {subject}"

        # HTML Body with Buttons
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <div style="background: #1a1a2e; color: white; padding: 20px; text-align: center;">
                    <h1 style="margin: 0; font-size: 24px;">🚨 AlertX Security Alert</h1>
                </div>
                <div style="padding: 20px;">
                    <h2 style="color: #e94560;">{subject}</h2>
                    <p>{body.replace('\\n', '<br>')}</p>
                    
                    <div style="margin: 30px 0; padding: 20px; background: #f9f9f9; border-radius: 8px; text-align: center;">
                        <h3 style="margin-top: 0;">⚡ AI Autonomous Dispatch</h3>
                        <p style="font-size: 14px; color: #666;">Click to trigger AI Voice Agent to call emergency services:</p>
                        
                        <div style="display: flex; justify-content: center; gap: 10px; flex-wrap: wrap;">
                            <a href="{PUBLIC_URL}/dispatch/police" style="display: inline-block; padding: 12px 20px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; margin: 5px;">🤖 Dispatch Police</a>
                            <a href="{PUBLIC_URL}/dispatch/ambulance" style="display: inline-block; padding: 12px 20px; background: #ef4444; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; margin: 5px;">🤖 Dispatch Ambulance</a>
                            <a href="{PUBLIC_URL}/dispatch/fire" style="display: inline-block; padding: 12px 20px; background: #f59e0b; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; margin: 5px;">🤖 Dispatch Fire</a>
                        </div>
                    </div>
                    
                    <p style="font-size: 12px; color: #999;">This is an automated AI alert from your AlertX Surveillance System.</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_content, 'html'))

        # Attach image frame if provided
        if frame is not None:
            _, buffer = cv2.imencode('.jpg', frame)
            image_attachment = MIMEImage(buffer.tobytes(), name="incident_evidence.jpg")
            msg.attach(image_attachment)

        # Connect and send
        logger.info(f"Connecting to {MAIL_SERVER}:465 (SSL Mode)...")
        try:
            with smtplib.SMTP_SSL(MAIL_SERVER, 465, timeout=15) as server:
                logger.info(f"SMTP Login for {MAIL_USERNAME}...")
                server.login(MAIL_USERNAME, MAIL_PASSWORD)
                server.send_message(msg)
                
            logger.info(f"✅ SUCCESS: Email alert sent to {target_email}")
            return True
        except Exception as smtp_err:
            logger.error(f"SMTP SSL Failed, trying fallback port 587... Error: {smtp_err}")
            with smtplib.SMTP(MAIL_SERVER, 587, timeout=15) as server:
                server.starttls()
                server.login(MAIL_USERNAME, MAIL_PASSWORD)
                server.send_message(msg)
            logger.info(f"✅ SUCCESS: Email alert sent via Fallback Port 587")
            return True

    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False
