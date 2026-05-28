"""Discord embeds for outreach replies + follow-up reminders.

Posts to a webhook on `#sales-and-outreach`, targeted into the dedicated
`outreach-replies` thread via the `?thread_id=` query parameter. No-op if
either env var is unset.

Three functions:
- `post_positive_reply` -- legacy, unclassified ping. Kept for backwards-compat
  callers; the new reply pipeline uses `post_classified_reply` instead.
- `post_classified_reply` -- includes LLM intent + drafted reply + Gmail link.
- `post_followup_reminder` -- daily nudge for replies that haven't closed yet.
"""

from __future__ import annotations

import httpx

from settings import settings

POSITIVE_COLOR = 0x2ECC71  # green
FOLLOWUP_COLOR = 0xF1C40F  # yellow
SNIPPET_LIMIT = 800
DRAFT_LIMIT = 1200

INTENT_COLORS = {
    "Interested":   0x2ECC71,  # green
    "Question":     0x3498DB,  # blue
    "HighPriority": 0xE74C3C,  # red
    "SoftNo":       0xF39C12,  # orange
    "WrongPerson":  0x95A5A6,  # gray
}


def _snippet(text: str | None, limit: int = SNIPPET_LIMIT) -> str:
    if not text:
        return "_(empty)_"
    t = text.strip()
    if len(t) <= limit:
        return t
    return t[:limit] + "..."


def _post_url() -> str | None:
    webhook = settings.DISCORD_OUTREACH_WEBHOOK_URL
    if not webhook:
        return None
    if settings.DISCORD_OUTREACH_THREAD_ID:
        sep = "&" if "?" in webhook else "?"
        return f"{webhook}{sep}thread_id={settings.DISCORD_OUTREACH_THREAD_ID}"
    return webhook


def post_positive_reply(
    *,
    lead_email: str,
    lead_company: str | None,
    campaign_name: str | None,
    positioning: str | None,
    instantly_category: str | None,
    body: str | None,
    reply_url: str | None,
) -> bool:
    """Legacy unclassified ping. Kept for backwards-compat with the older
    pipeline (before the LLM classifier was wired in)."""
    url = _post_url()
    if not url:
        return False

    fields = [
        {"name": "Lead", "value": lead_email or "_(unknown)_", "inline": True},
        {"name": "Company", "value": lead_company or "_(unknown)_", "inline": True},
        {"name": "Category", "value": instantly_category or "_(unlabeled)_", "inline": True},
        {"name": "Campaign", "value": campaign_name or "_(unknown)_", "inline": True},
        {"name": "Positioning", "value": positioning or "_(unset)_", "inline": True},
    ]

    embed: dict = {
        "title": "Positive reply",
        "color": POSITIVE_COLOR,
        "description": _snippet(body),
        "fields": fields,
    }
    if reply_url:
        embed["url"] = reply_url

    response = httpx.post(url, json={"embeds": [embed]}, timeout=10.0)
    response.raise_for_status()
    return True


def post_classified_reply(
    *,
    lead_email: str,
    lead_company: str | None,
    campaign_name: str | None,
    positioning: str | None,
    intent: str,
    confidence: float,
    key_message: str | None,
    body: str | None,
    drafted_reply: str | None,
    gmail_url: str | None,
    reply_url: str | None,
) -> bool:
    """Post the enhanced embed: intent + confidence + drafted reply + Gmail link."""
    url = _post_url()
    if not url:
        return False

    color = INTENT_COLORS.get(intent, POSITIVE_COLOR)

    desc_parts: list[str] = []
    if key_message:
        desc_parts.append(f"**What they said:** {key_message}")
    if drafted_reply:
        desc_parts.append(f"\n**Drafted reply:**\n```\n{_snippet(drafted_reply, DRAFT_LIMIT)}\n```")
    elif body:
        # No draft (drafter failed or skipped) -- show their reply body so Pang has context.
        desc_parts.append(f"\n**Their reply:**\n{_snippet(body)}")

    fields = [
        {"name": "Lead", "value": lead_email or "_(unknown)_", "inline": True},
        {"name": "Company", "value": lead_company or "_(unknown)_", "inline": True},
        {"name": "Intent", "value": f"{intent} ({confidence:.0%})", "inline": True},
        {"name": "Campaign", "value": campaign_name or "_(unknown)_", "inline": True},
        {"name": "Positioning", "value": positioning or "_(unset)_", "inline": True},
    ]
    if gmail_url:
        fields.append({"name": "Gmail draft", "value": f"[Open thread]({gmail_url})", "inline": True})

    embed: dict = {
        "title": f"Reply -- {intent}",
        "color": color,
        "description": "\n".join(desc_parts) if desc_parts else "_(no summary)_",
        "fields": fields,
    }
    # Title-link goes to the Gmail draft if we have one, else Instantly's reply URL.
    if gmail_url:
        embed["url"] = gmail_url
    elif reply_url:
        embed["url"] = reply_url

    response = httpx.post(url, json={"embeds": [embed]}, timeout=10.0)
    response.raise_for_status()
    return True


def post_followup_reminder(
    *,
    lead_email: str,
    lead_company: str | None,
    intent: str | None,
    key_message: str | None,
    follow_up_count: int,
    max_pings: int,
    gmail_thread_id: str | None,
    replied_at: str | None,
) -> bool:
    """Yellow follow-up nudge. Title shows N/max so Pang sees the ping budget left."""
    url = _post_url()
    if not url:
        return False

    next_count = follow_up_count + 1

    fields = [
        {"name": "Lead", "value": lead_email or "_(unknown)_", "inline": True},
        {"name": "Company", "value": lead_company or "_(unknown)_", "inline": True},
        {"name": "Intent", "value": intent or "_(unclassified)_", "inline": True},
        {"name": "Reply landed", "value": replied_at or "_(unknown)_", "inline": True},
    ]
    if gmail_thread_id:
        thread_url = f"https://mail.google.com/mail/u/0/#all/{gmail_thread_id}"
        fields.append({"name": "Gmail thread", "value": f"[Open]({thread_url})", "inline": True})

    embed: dict = {
        "title": f"Follow up reminder ({next_count}/{max_pings})",
        "color": FOLLOWUP_COLOR,
        "description": key_message or "_(no summary)_",
        "fields": fields,
    }
    if gmail_thread_id:
        embed["url"] = f"https://mail.google.com/mail/u/0/#all/{gmail_thread_id}"

    response = httpx.post(url, json={"embeds": [embed]}, timeout=10.0)
    response.raise_for_status()
    return True
