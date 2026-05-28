"""PostgREST writers for the four outreach_* tables.

Same auth + on_conflict pattern as ops_os/integrations/fathom/supabase_writer.
The poller never touches `positioning` or `created_at` — those are owned by
the operator (set manually in Supabase Studio after first poll). All other
columns are merge-replaced on conflict.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import httpx

from settings import settings

CAMPAIGNS_TABLE = "outreach_campaigns"
STEPS_TABLE = "outreach_sequence_steps"
METRICS_TABLE = "outreach_daily_step_metrics"
REPLIES_TABLE = "outreach_replies"

REPLY_BODY_LIMIT = 20_000


def _headers(prefer: str) -> dict[str, str]:
    return {
        "apikey": settings.SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _rest_base() -> str:
    return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1"


def _truncate(text: str | None, limit: int = REPLY_BODY_LIMIT) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[truncated]"


def upsert_campaign(campaign_id: str, name: str, status: str | None, started_at: str | None) -> dict:
    """Create-or-update the campaigns row. Does NOT touch `positioning` or
    `created_at` — `?columns=` restricts which fields we send. Operator owns
    positioning and sets it manually after the first poll lands the row.
    """
    row = {
        "id": campaign_id,
        "name": name,
        "status": status or "",
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    url = (
        f"{_rest_base()}/{CAMPAIGNS_TABLE}"
        "?on_conflict=id&columns=id,name,status,started_at,updated_at"
    )
    response = httpx.post(
        url,
        headers=_headers("resolution=merge-duplicates,return=representation"),
        json=[row],
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return (data or [row])[0]


def upsert_sequence_step(campaign_id: str, step_index: int, subject: str | None, body_preview: str | None) -> dict:
    row = {
        "campaign_id": campaign_id,
        "step_index": step_index,
        "subject": subject or "",
        "body_preview": _truncate(body_preview, 500),
    }
    url = f"{_rest_base()}/{STEPS_TABLE}?on_conflict=campaign_id,step_index"
    response = httpx.post(
        url,
        headers=_headers("resolution=merge-duplicates,return=representation"),
        json=[row],
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return (data or [row])[0]


def upsert_daily_metrics(
    campaign_id: str,
    step_index: int,
    metrics_date: date,
    *,
    emails_sent: int = 0,
    replies: int = 0,
    unsubscribes: int = 0,
    raw_snapshot: dict | None = None,
) -> dict:
    row = {
        "campaign_id": campaign_id,
        "step_index": step_index,
        "date": metrics_date.isoformat(),
        "emails_sent": emails_sent,
        "replies": replies,
        "unsubscribes": unsubscribes,
        "raw_snapshot": raw_snapshot or {},
    }
    url = f"{_rest_base()}/{METRICS_TABLE}?on_conflict=campaign_id,step_index,date"
    response = httpx.post(
        url,
        headers=_headers("resolution=merge-duplicates,return=representation"),
        json=[row],
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return (data or [row])[0]


def insert_reply(
    *,
    instantly_lead_id: str | None,
    lead_email: str,
    lead_company: str | None,
    campaign_id: str | None,
    step_index: int | None,
    replied_at: str,
    body: str | None,
    instantly_category: str | None,
    is_positive: bool,
    reply_url: str | None,
    raw_payload: dict,
) -> dict:
    row = {
        "instantly_lead_id": instantly_lead_id,
        "lead_email": lead_email,
        "lead_company": lead_company,
        "campaign_id": campaign_id,
        "step_index": step_index,
        "replied_at": replied_at,
        "body": _truncate(body),
        "instantly_category": instantly_category,
        "is_positive": is_positive,
        "reply_url": reply_url,
        "raw_payload": raw_payload,
    }
    url = f"{_rest_base()}/{REPLIES_TABLE}"
    response = httpx.post(
        url,
        headers=_headers("return=representation"),
        json=[row],
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return (data or [row])[0]


def fetch_campaigns_with_metrics() -> list[dict[str, Any]]:
    """Used by the dashboard list view. Joins campaigns with rolled-up
    lifetime totals via PostgREST embed.
    """
    url = (
        f"{_rest_base()}/{CAMPAIGNS_TABLE}"
        "?select=id,name,positioning,status,started_at,"
        f"{METRICS_TABLE}(emails_sent,replies,unsubscribes)"
        "&order=started_at.desc.nullslast"
    )
    response = httpx.get(url, headers=_headers("count=exact"), timeout=30.0)
    response.raise_for_status()
    return response.json() or []


def fetch_campaign(campaign_id: str) -> dict[str, Any] | None:
    url = (
        f"{_rest_base()}/{CAMPAIGNS_TABLE}"
        f"?id=eq.{campaign_id}&select=*&limit=1"
    )
    response = httpx.get(url, headers=_headers("count=exact"), timeout=30.0)
    response.raise_for_status()
    rows = response.json() or []
    return rows[0] if rows else None


def fetch_steps(campaign_id: str) -> list[dict[str, Any]]:
    url = (
        f"{_rest_base()}/{STEPS_TABLE}"
        f"?campaign_id=eq.{campaign_id}&order=step_index.asc"
    )
    response = httpx.get(url, headers=_headers("count=exact"), timeout=30.0)
    response.raise_for_status()
    return response.json() or []


def fetch_step_metrics(campaign_id: str, days: int = 30) -> list[dict[str, Any]]:
    url = (
        f"{_rest_base()}/{METRICS_TABLE}"
        f"?campaign_id=eq.{campaign_id}&order=date.desc,step_index.asc&limit={days * 20}"
    )
    response = httpx.get(url, headers=_headers("count=exact"), timeout=30.0)
    response.raise_for_status()
    return response.json() or []


def fetch_recent_replies(campaign_id: str, limit: int = 50) -> list[dict[str, Any]]:
    url = (
        f"{_rest_base()}/{REPLIES_TABLE}"
        f"?campaign_id=eq.{campaign_id}&order=replied_at.desc&limit={limit}"
    )
    response = httpx.get(url, headers=_headers("count=exact"), timeout=30.0)
    response.raise_for_status()
    return response.json() or []


# ---------- reply-handler writers (classifier + drafter + follow-up) ----------


def update_reply_with_classification(
    reply_id: str,
    *,
    intent: str,
    confidence: float,
    key_message: str,
) -> dict:
    """Patch a stored reply with the LLM classifier output."""
    url = f"{_rest_base()}/{REPLIES_TABLE}?id=eq.{reply_id}"
    payload = {
        "intent": intent,
        "confidence": confidence,
        "key_message": _truncate(key_message, 2000),
    }
    response = httpx.patch(
        url,
        headers=_headers("return=representation"),
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return (data or [payload])[0]


def update_reply_with_draft(
    reply_id: str,
    *,
    gmail_thread_id: str | None,
    gmail_draft_id: str | None,
    recommended_reply: str | None,
) -> dict:
    """Patch a stored reply with the Gmail draft + drafted body text."""
    url = f"{_rest_base()}/{REPLIES_TABLE}?id=eq.{reply_id}"
    payload = {
        "gmail_thread_id": gmail_thread_id,
        "gmail_draft_id": gmail_draft_id,
        "recommended_reply": _truncate(recommended_reply, REPLY_BODY_LIMIT),
    }
    response = httpx.patch(
        url,
        headers=_headers("return=representation"),
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return (data or [payload])[0]


def fetch_replies_due_for_followup(*, cutoff_iso: str) -> list[dict[str, Any]]:
    """Returns positive replies that need a follow-up Discord ping.

    Filters:
      - is_positive = true
      - intent NOT IN ('OOO', 'OptOut')
      - follow_up_count < 3
      - replied_at < cutoff_iso
      - (last_follow_up_at IS NULL OR last_follow_up_at < cutoff_iso)

    cutoff_iso is normally `now - 24h` -- the daily beat task passes it.
    """
    from urllib.parse import quote

    encoded = quote(cutoff_iso, safe="")
    url = (
        f"{_rest_base()}/{REPLIES_TABLE}"
        "?is_positive=eq.true"
        "&follow_up_count=lt.3"
        f"&replied_at=lt.{encoded}"
        "&intent=not.in.(OOO,OptOut)"
        f"&or=(last_follow_up_at.is.null,last_follow_up_at.lt.{encoded})"
        "&order=replied_at.desc"
        "&limit=50"
    )
    response = httpx.get(url, headers=_headers("count=exact"), timeout=30.0)
    response.raise_for_status()
    return response.json() or []


def mark_followup_sent(reply_id: str, *, now_iso: str, new_count: int) -> dict:
    """After a follow-up ping fires, bump follow_up_count + last_follow_up_at."""
    url = f"{_rest_base()}/{REPLIES_TABLE}?id=eq.{reply_id}"
    payload = {
        "follow_up_count": new_count,
        "last_follow_up_at": now_iso,
    }
    response = httpx.patch(
        url,
        headers=_headers("return=representation"),
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return (data or [payload])[0]
