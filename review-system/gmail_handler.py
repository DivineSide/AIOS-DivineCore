"""
Gmail handler. Sends email via Gmail API using OAuth2 credentials from Google Cloud.
Same project as the one already set up — just enable Gmail API and add the scope.
Mock mode for local testing without sending real emails.
"""
import logging
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_SENDER_EMAIL, DEBUG

logger = logging.getLogger(__name__)

class GmailHandler:
    def __init__(self):
        self.sender_email = GMAIL_SENDER_EMAIL
        self.mock_mode = DEBUG or not GMAIL_REFRESH_TOKEN

        if not self.mock_mode:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            creds = Credentials(
                token=None,
                refresh_token=GMAIL_REFRESH_TOKEN,
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET,
                token_uri="https://oauth2.googleapis.com/token"
            )
            self.service = build("gmail", "v1", credentials=creds)
        else:
            logger.warning("Gmail running in MOCK mode")

    def send_email(self, to_email: str, subject: str, body: str, metadata: dict = None) -> dict:
        """
        Send email via Gmail API (or mock in dev mode).

        Returns:
            { "email_id": "...", "status": "sent"|"failed", "to": "...", "timestamp": "..." }
        """
        try:
            if self.mock_mode:
                email_id = f"gmail_mock_{datetime.utcnow().timestamp()}"
                logger.info(f"[MOCK] Email to {to_email} | {subject}")
                return {
                    "email_id": email_id,
                    "status": "sent",
                    "to": to_email,
                    "timestamp": datetime.utcnow().isoformat(),
                    "mode": "MOCK"
                }

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender_email
            msg["To"] = to_email
            msg.attach(MIMEText(body, "plain"))

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            sent = self.service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()

            logger.info(f"Email sent to {to_email}, id: {sent['id']}")
            return {
                "email_id": sent["id"],
                "status": "sent",
                "to": to_email,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return {
                "email_id": None,
                "status": "failed",
                "error": str(e),
                "to": to_email,
                "timestamp": datetime.utcnow().isoformat()
            }


# Singleton
gmail = GmailHandler()
