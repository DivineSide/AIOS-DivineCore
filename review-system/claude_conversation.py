"""
Claude conversation engine. Reads replies, classifies sentiment, generates responses.
"""
import logging
from datetime import datetime
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

class ClaudeConversationEngine:
    def __init__(self):
        self.client = Anthropic()
        self.model = "claude-3-5-sonnet-20241022"

    def process_reply(self, reply_text: str, student_name: str, course_name: str,
                      sharon_voice_context: str = None) -> dict:
        """
        Process a student reply: classify sentiment + generate response.

        Args:
            reply_text: Student's reply text
            student_name: Student's name (for personalization)
            course_name: Course/batch name (for context)
            sharon_voice_context: Optional context about Sharon's tone/style

        Returns:
            {
                "sentiment": "positive" | "neutral" | "negative",
                "confidence": 0.95,  # 0-1
                "response_text": "Your reply from Sharon...",
                "next_action": "ask_referral" | "just_thank" | "acknowledge_feedback",
                "reasoning": "Why this sentiment/action was chosen"
            }
        """
        prompt = f"""You are analyzing a student's reply to a review request for a coaching institute.

STUDENT REPLY: "{reply_text}"
STUDENT NAME: {student_name}
COURSE NAME: {course_name}

TASK 1: Classify the sentiment
- Positive: They're happy, will likely leave a good review, or already mentioned the coaching helped
- Neutral: They're indifferent, didn't say much, or just acknowledged
- Negative: They're unhappy, complained, or said something critical

TASK 2: Determine next action
- ask_referral: Only if POSITIVE sentiment. Ask them to refer a friend/family
- just_thank: If NEUTRAL. Thank them for their time
- acknowledge_feedback: If NEGATIVE. Acknowledge their feedback, don't push for review

TASK 3: Generate Sharon's response
- Keep it under 80 words
- Sound genuine, not templated
- Use their name
- If positive: thank them + ask for referral (phone/email of someone they know)
- If neutral: thank them + wish them well
- If negative: acknowledge + ask if there's anything you (Sharon) can help with

RESPONSE FORMAT:
SENTIMENT: [positive|neutral|negative]
CONFIDENCE: [0.0-1.0]
NEXT_ACTION: [ask_referral|just_thank|acknowledge_feedback]
RESPONSE: [Sharon's message]
REASONING: [One sentence explaining the classification]"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text
            parsed = self._parse_response(response_text)

            logger.info(f"Processed reply from {student_name}: sentiment={parsed['sentiment']}")
            return parsed

        except Exception as e:
            logger.error(f"Failed to process reply: {str(e)}")
            return {
                "sentiment": "neutral",
                "confidence": 0.0,
                "response_text": f"Thank you for your response, {student_name}!",
                "next_action": "just_thank",
                "reasoning": "Error in processing; defaulted to neutral",
                "error": str(e)
            }

    def _parse_response(self, claude_response: str) -> dict:
        """Parse Claude's structured response."""
        lines = claude_response.strip().split('\n')
        result = {
            "sentiment": "neutral",
            "confidence": 0.5,
            "response_text": "",
            "next_action": "just_thank",
            "reasoning": ""
        }

        for line in lines:
            if line.startswith("SENTIMENT:"):
                sentiment = line.split(":", 1)[1].strip().lower()
                if sentiment in ["positive", "neutral", "negative"]:
                    result["sentiment"] = sentiment

            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                    result["confidence"] = min(1.0, max(0.0, confidence))
                except ValueError:
                    pass

            elif line.startswith("NEXT_ACTION:"):
                action = line.split(":", 1)[1].strip().lower()
                if action in ["ask_referral", "just_thank", "acknowledge_feedback"]:
                    result["next_action"] = action

            elif line.startswith("RESPONSE:"):
                # Response might span multiple lines
                result["response_text"] = line.split(":", 1)[1].strip()

            elif line.startswith("REASONING:"):
                result["reasoning"] = line.split(":", 1)[1].strip()

        # If response_text wasn't captured properly, extract it
        if not result["response_text"] and "RESPONSE:" in claude_response:
            parts = claude_response.split("RESPONSE:")
            if len(parts) > 1:
                result["response_text"] = parts[1].split("\n")[0].strip()
                # Get additional lines if response spans multiple
                response_section = parts[1].split("REASONING:")[0].strip()
                result["response_text"] = response_section

        return result


# Singleton instance
claude_engine = ClaudeConversationEngine()
