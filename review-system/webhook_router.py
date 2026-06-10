"""
Webhook router. Receives SMS/email replies, routes to Claude for processing.
"""
import logging
from datetime import datetime
from typing import Callable
from twilio_handler import twilio
from brevo_handler import brevo
from claude_conversation import claude_engine
from gbp_oauth import gbp_handler

logger = logging.getLogger(__name__)

class WebhookRouter:
    def __init__(self):
        self.handlers = {}
        self.reply_queue = []  # For async processing if needed

    def handle_sms_reply(self, twilio_payload: dict, request_url: str,
                         request_signature: str) -> dict:
        """
        Handle incoming SMS reply from Twilio.

        Args:
            twilio_payload: POST data from Twilio webhook
            request_url: Full request URL (for validation)
            request_signature: X-Twilio-Signature header

        Returns:
            {
                "status": "success" | "error",
                "message": "...",
                "processing_id": "..."
            }
        """
        # Validate webhook came from Twilio
        if not twilio.validate_twilio_webhook(request_url, twilio_payload, request_signature):
            logger.error("Invalid Twilio webhook signature")
            return {
                "status": "error",
                "message": "Invalid signature"
            }

        # Parse SMS reply
        reply = twilio.parse_sms_reply(twilio_payload)

        logger.info(f"SMS reply received from {reply['from_phone']}: {reply['message_text'][:50]}...")

        # Route to processing
        return self._route_reply_to_claude(
            reply_text=reply["message_text"],
            from_contact=reply["from_phone"],
            channel="sms",
            sms_id=reply["sms_id"]
        )

    def handle_email_reply(self, brevo_payload: dict) -> dict:
        """
        Handle incoming email reply (placeholder for future implementation).
        Brevo doesn't natively webhook email replies, so this is a stub.

        Returns:
            {
                "status": "success" | "error",
                "message": "...",
                "processing_id": "..."
            }
        """
        # Placeholder: actual implementation depends on inbound email setup
        logger.warning("Email reply handling not yet implemented")
        return {
            "status": "error",
            "message": "Email reply handling not yet implemented"
        }

    def _route_reply_to_claude(self, reply_text: str, from_contact: str,
                                channel: str, sms_id: str = None, email_id: str = None) -> dict:
        """
        Route reply to Claude for processing (sentiment classification + response generation).

        Args:
            reply_text: Student's reply
            from_contact: Phone or email
            channel: "sms" or "email"
            sms_id: Twilio message ID (if SMS)
            email_id: Brevo message ID (if email)

        Returns:
            {
                "status": "success" | "error",
                "message": "...",
                "processing_id": "...",
                "sentiment": "positive" | "neutral" | "negative" (if success),
                "next_action": "ask_referral" | "just_thank" | "acknowledge_feedback" (if success)
            }
        """
        try:
            # For now, use placeholder student/course info
            # In production, we'd look up the student by from_contact
            student_name = "Student"  # Would be looked up from DB
            course_name = "Course"    # Would be looked up from DB

            # Process through Claude
            claude_result = claude_engine.process_reply(
                reply_text=reply_text,
                student_name=student_name,
                course_name=course_name
            )

            processing_id = f"{channel}_{datetime.utcnow().timestamp()}"

            logger.info(f"Processed reply: {processing_id}, sentiment: {claude_result['sentiment']}")

            return {
                "status": "success",
                "message": "Reply processed successfully",
                "processing_id": processing_id,
                "sentiment": claude_result["sentiment"],
                "next_action": claude_result["next_action"],
                "claude_response": claude_result["response_text"]
            }

        except Exception as e:
            logger.error(f"Failed to process reply: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "processing_id": None
            }

    def send_claude_reply(self, to_contact: str, channel: str, response_text: str,
                         original_sms_id: str = None, original_email_id: str = None) -> dict:
        """
        Send Claude's generated response back to the student.

        Args:
            to_contact: Phone or email to send to
            channel: "sms" or "email"
            response_text: Claude's reply
            original_sms_id: If replying to SMS
            original_email_id: If replying to email

        Returns:
            {
                "success": True|False,
                "message_id": "...",
                "error": "..." (if failed)
            }
        """
        try:
            if channel == "sms":
                result = twilio.send_sms(to_contact, response_text)
                return {
                    "success": result["status"] in ["queued", "sending", "sent"],
                    "message_id": result.get("sms_id"),
                    "error": result.get("error")
                }

            elif channel == "email":
                # Send via email
                subject = "Response to Your Review"
                html_content = f"<p>{response_text}</p>"
                result = brevo.send_email(to_contact, subject, html_content)
                return {
                    "success": result["status"] == "sent",
                    "message_id": result.get("email_id"),
                    "error": result.get("error")
                }

            else:
                return {
                    "success": False,
                    "error": f"Unknown channel: {channel}"
                }

        except Exception as e:
            logger.error(f"Failed to send reply: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


# Singleton instance
webhook_router = WebhookRouter()
