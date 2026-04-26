import os
import logging
import cv2
import base64
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition

logger = logging.getLogger("alertx.email_api")

def send_email_api(subject, body, frame=None, recipient=None):
    """
    Sends email via SendGrid API (Port 443).
    Bypasses Hugging Face SMTP blocks.
    """
    api_key = os.getenv("SENDGRID_API_KEY")
    sender = os.getenv("MAIL_USERNAME") # Your verified SendGrid sender email
    target = recipient or os.getenv("MAIL_RECIPIENT")

    if not api_key or not sender or not target:
        logger.warning("[STUB] Email API: Credentials missing.")
        return False

    message = Mail(
        from_email=sender,
        to_emails=target,
        subject=f"🛡️ AlertX: {subject}",
        html_content=f"<strong>{subject}</strong><br><br>{body.replace('\\n', '<br>')}"
    )

    if frame is not None:
        _, buffer = cv2.imencode('.jpg', frame)
        encoded_file = base64.b64encode(buffer).decode()
        attached_file = Attachment(
            FileContent(encoded_file),
            FileName('incident.jpg'),
            FileType('image/jpeg'),
            Disposition('attachment')
        )
        message.add_attachment(attached_file)

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        logger.info(f"✅ Email API Success: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"❌ Email API Failed: {e}")
        return False
