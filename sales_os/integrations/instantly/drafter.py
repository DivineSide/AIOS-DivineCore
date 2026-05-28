"""Claude-based reply drafter.

Uses OpenRouter -- Claude Sonnet 4.6 by default (settings.REPLY_DRAFTER_MODEL)
for voice quality on cold-reply drafts. Loads Pang's voice profile via
voice_loader on every call (low volume, fresh-each-call is fine).

Skips OOO and OptOut intents -- returns empty string for those.
"""

from __future__ import annotations

from openai import OpenAI

from settings import settings

from . import prompts, voice_loader

SKIP_INTENTS = {"OOO", "OptOut"}


def _client() -> OpenAI:
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


def draft(
    *,
    intent: str,
    key_message: str,
    reply_body: str,
    lead_first_name: str | None,
    lead_company: str | None,
    lead_email: str,
) -> str:
    """Returns the drafted reply body. Empty string if intent is OOO/OptOut."""
    if intent in SKIP_INTENTS:
        return ""

    intent_rules = prompts.INTENT_RULES.get(intent) or prompts.INTENT_RULES["Question"]
    system_prompt = prompts.DRAFTER_SYSTEM_TEMPLATE.format(
        pang_voice=voice_loader.load_pang_voice(),
        intent_rules=intent_rules,
    )
    user_prompt = prompts.DRAFTER_USER_TEMPLATE.format(
        intent=intent,
        key_message=key_message,
        reply_body=reply_body,
        lead_first_name=lead_first_name or "(unknown)",
        lead_company=lead_company or "(unknown)",
        lead_email=lead_email,
        calendly_url=settings.DIVINESIDE_CALENDLY_URL,
    )
    response = _client().chat.completions.create(
        model=settings.REPLY_DRAFTER_MODEL,
        temperature=0.5,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (response.choices[0].message.content or "").strip()
