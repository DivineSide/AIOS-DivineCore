"""
Generic trigger detector. Polls for course-end events from Sharon's system.
Specific implementations per platform (Kajabi, Teachable, etc.) extend this.
"""
import logging
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)

class BaseTriggerDetector:
    """
    Base class for detecting course-end triggers.
    Subclasses implement platform-specific logic.
    """

    def detect_triggers(self) -> List[dict]:
        """
        Poll for new course-end events.

        Returns:
            [
                {
                    "student_id": "...",
                    "student_name": "...",
                    "student_email": "...",
                    "student_phone": "...",
                    "course_id": "...",
                    "course_name": "...",
                    "course_result": "pass" | "completed" | "score:85",
                    "trigger_timestamp": datetime,
                    "trigger_source": "kajabi" | "teachable" | "manual"
                }
            ]
        """
        raise NotImplementedError("Subclasses must implement detect_triggers()")


class ManualTriggerDetector(BaseTriggerDetector):
    """
    Manual trigger detection via webhook or direct API call.
    Used when Sharon's system doesn't have native integration.
    """

    def __init__(self):
        self.pending_triggers = []

    def enqueue_trigger(self, trigger_data: dict) -> dict:
        """
        Manually enqueue a course-end trigger (webhook endpoint).

        Args:
            trigger_data: {
                "student_id": "...",
                "student_name": "...",
                "student_email": "...",
                "student_phone": "...",
                "course_id": "...",
                "course_name": "...",
                "course_result": "pass" | "completed"
            }

        Returns:
            {
                "success": True|False,
                "trigger_id": "...",
                "message": "..."
            }
        """
        try:
            trigger = {
                **trigger_data,
                "trigger_id": f"trigger_{datetime.utcnow().timestamp()}",
                "trigger_timestamp": datetime.utcnow().isoformat(),
                "trigger_source": "manual"
            }

            self.pending_triggers.append(trigger)
            logger.info(f"Enqueued trigger: {trigger['trigger_id']} for {trigger_data.get('student_name')}")

            return {
                "success": True,
                "trigger_id": trigger["trigger_id"],
                "message": "Trigger enqueued successfully"
            }

        except Exception as e:
            logger.error(f"Failed to enqueue trigger: {str(e)}")
            return {
                "success": False,
                "message": str(e)
            }

    def detect_triggers(self) -> List[dict]:
        """Get all pending triggers and clear the queue."""
        triggers = self.pending_triggers.copy()
        self.pending_triggers.clear()
        return triggers


# Singleton instance
manual_detector = ManualTriggerDetector()
