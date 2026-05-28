"""Claude-based intent classifier for Instantly replies.

Uses OpenRouter -- GPT-4o-mini by default (settings.REPLY_CLASSIFIER_MODEL).
Returns the 7-bucket classification + confidence + 1-2 sentence summary.
"""

from __future__ import annotations

import json
from typing import TypedDict

from openai import OpenAI

from settings import settings

from . import prompts


class Classification(TypedDict):
    intent: str
    confidence: float
    key_message: str


def _client() -> OpenAI:
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


def classify(reply_body: str) -> Classification:
    """Classify a reply into one of 7 intents. Falls back to Question intent
    on JSON parse error so the pipeline doesn't crash."""
    if not reply_body or not reply_body.strip():
        return {"intent": "OOO", "confidence": 0.0, "key_message": "empty reply body"}

    response = _client().chat.completions.create(
        model=settings.REPLY_CLASSIFIER_MODEL,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompts.CLASSIFIER_SYSTEM},
            {"role": "user", "content": prompts.CLASSIFIER_USER_TEMPLATE.format(reply_body=reply_body)},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"intent": "Question", "confidence": 0.0, "key_message": "(classifier returned non-JSON)"}

    intent = parsed.get("intent", "Question")
    if intent not in prompts.INTENTS:
        intent = "Question"
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    key_message = parsed.get("key_message") or ""
    return {"intent": intent, "confidence": confidence, "key_message": key_message}
