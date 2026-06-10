"""
Twilio SMS handler. Sends SMS via Twilio, receives replies via webhook.
Mock mode for testing without Twilio credits.
"""
import logging
from datetime import datetime
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, DEBUG

logger = logging.getLogger(__name__)

class TwilioHandler:
    def __init__(self):
        self.from_number = TWILIO_PHONE_NUMBER
        self.mock_mode = DEBUG or TWILIO_ACCOUNT_SID == "mock_account_sid"

        if not self.mock_mode:
            from twilio.rest import Client
            from twilio.request_validator import RequestValidator
            self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            self.validator = RequestValidator(TWILIO_AUTH_TOKEN)
        else:
            logger.warning("Twilio running in MOCK mode")

    def send_sms(self, to_phone: str, message_text: str, metadata: dict = None) -> dict:
        """
        Send SMS via Twilio (or mock in dev mode).

        Args:
            to_phone: Phone number (E.164 format, e.g., "+14155552671")
            message_text: SMS body (max 160 chars, Twilio handles multi-part)
            metadata: Optional dict with student_id, course_id, etc. for logging

        Returns:
            {
                "sms_id": "SMxxxxx",
                "status": "queued" | "sending" | "sent" | "failed",
                "to": "+1xxx",
                "timestamp": datetime
            }
        """
        try:
            if self.mock_mode:
                # Mock mode: simulate successful SMS send
                sms_id = f"SM_mock_{datetime.utcnow().timestamp()}"
                result = {
                    "sms_id": sms_id,
                    "status": "sent",
                    "to": to_phone,
                    "timestamp": datetime.utcnow().isoformat(),
                    "metadata": metadata or {},
                    "mode": "MOCK"
                }
                logger.info(f"[MOCK] SMS sent: {sms_id} to {to_phone}: {message_text[:50]}...")
                return result
            else:
                # Real Twilio
                from twilio.rest import Client
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                message = client.messages.create(
                    body=message_text,
                    from_=self.from_number,
                    to=to_phone
                )

                result = {
                    "sms_id": message.sid,
                    "status": message.status,
                    "to": message.to,
                    "timestamp": datetime.utcnow().isoformat(),
                    "metadata": metadata or {}
                }

                logger.info(f"SMS sent: {message.sid} to {to_phone}")
                return result

        except Exception as e:
            logger.error(f"Failed to send SMS to {to_phone}: {str(e)}")
            return {
                "sms_id": None,
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def validate_twilio_webhook(self, request_url: str, request_data: dict, request_signature: str) -> bool:
        """
        Validate that webhook came from Twilio (or skip in mock mode).

        Args:
            request_url: Full request URL (https://example.com/webhooks/sms)
            request_data: POST data dict
            request_signature: X-Twilio-Signature header value

        Returns:
            True if valid, False otherwise
        """
        if self.mock_mode:
            logger.debug("[MOCK] Twilio webhook validation skipped")
            return True
        else:
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(TWILIO_AUTH_TOKEN)
            return validator.validate(request_url, request_data, request_signature)

    def parse_sms_reply(self, twilio_payload: dict) -> dict:
        """
        Parse SMS reply from Twilio webhook.

        Args:
            twilio_payload: POST data from Twilio webhook

        Returns:
            {
                "sms_id": "SMxxxxx",
                "from_phone": "+1xxx",
                "message_text": "...",
                "timestamp": datetime,
                "num_media": 0  # If they attached media (images, etc.)
            }
        """
        return {
            "sms_id": twilio_payload.get("MessageSid"),
            "from_phone": twilio_payload.get("From"),
            "message_text": twilio_payload.get("Body", "").strip(),
            "timestamp": datetime.utcnow().isoformat(),
            "num_media": int(twilio_payload.get("NumMedia", 0))
        }


# Singleton instance
twilio = TwilioHandler()
