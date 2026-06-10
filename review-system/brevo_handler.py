"""
Brevo email handler. Sends email via Brevo, receives replies via webhook.
Mock mode for testing without Brevo API access.
"""
import logging
from datetime import datetime
from config import BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME, DEBUG

logger = logging.getLogger(__name__)

class BrevoHandler:
    def __init__(self):
        self.sender_email = BREVO_SENDER_EMAIL
        self.sender_name = BREVO_SENDER_NAME
        self.mock_mode = DEBUG or BREVO_API_KEY == "get_from_brevo_settings"

        if not self.mock_mode:
            from sib_api_v3_sdk import Configuration, ApiClient, TransactionalEmailsApi
            configuration = Configuration()
            configuration.api_key['api-key'] = BREVO_API_KEY
            self.api_client = ApiClient(configuration)
            self.api_instance = TransactionalEmailsApi(self.api_client)
        else:
            logger.warning("Brevo running in MOCK mode")

    def send_email(self, to_email: str, subject: str, html_content: str,
                   text_content: str = None, metadata: dict = None) -> dict:
        """
        Send email via Brevo (or mock in dev mode).

        Args:
            to_email: Recipient email
            subject: Email subject
            html_content: HTML email body
            text_content: Plain text fallback (optional)
            metadata: Optional dict with student_id, course_id, etc.

        Returns:
            {
                "email_id": "message_id_from_brevo",
                "status": "sent" | "failed",
                "to": "recipient@example.com",
                "timestamp": datetime
            }
        """
        try:
            if self.mock_mode:
                # Mock mode: simulate successful email send
                email_id = f"email_mock_{datetime.utcnow().timestamp()}"
                result = {
                    "email_id": email_id,
                    "status": "sent",
                    "to": to_email,
                    "timestamp": datetime.utcnow().isoformat(),
                    "metadata": metadata or {},
                    "mode": "MOCK"
                }
                logger.info(f"[MOCK] Email sent to {to_email}, subject: {subject}")
                return result
            else:
                # Real Brevo
                from sib_api_v3_sdk import SendSmtpEmail
                send_smtp_email = SendSmtpEmail(
                    to=[{"email": to_email}],
                    sender={"name": self.sender_name, "email": self.sender_email},
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content or subject
                )

                response = self.api_instance.send_transac_email(send_smtp_email)

                result = {
                    "email_id": response.message_id if hasattr(response, 'message_id') else str(response),
                    "status": "sent",
                    "to": to_email,
                    "timestamp": datetime.utcnow().isoformat(),
                    "metadata": metadata or {}
                }

                logger.info(f"Email sent to {to_email}, message_id: {result['email_id']}")
                return result

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return {
                "email_id": None,
                "status": "failed",
                "error": str(e),
                "to": to_email,
                "timestamp": datetime.utcnow().isoformat()
            }

    def parse_email_reply(self, brevo_payload: dict) -> dict:
        """
        Parse email reply from Brevo webhook (reply tracking via email).
        Brevo doesn't natively track email replies via webhook like SMS.
        This is a placeholder for future implementation (e.g., parsing inbound emails).

        For now, replies come via a dedicated inbound email address or manual entry.

        Args:
            brevo_payload: Webhook data from Brevo

        Returns:
            {
                "email_id": "message_id",
                "from_email": "student@example.com",
                "message_text": "...",
                "timestamp": datetime
            }
        """
        # Placeholder: actual implementation depends on Brevo inbound email setup
        return {
            "email_id": brevo_payload.get("message_id"),
            "from_email": brevo_payload.get("from_email"),
            "message_text": brevo_payload.get("body", "").strip(),
            "timestamp": datetime.utcnow().isoformat()
        }


# Singleton instance
brevo = BrevoHandler()
