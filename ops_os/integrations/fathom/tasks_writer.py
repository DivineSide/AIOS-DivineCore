from datetime import datetime, timedelta, timezone

import httpx

from settings import settings
from team import resolve_by_email, resolve_by_name

DEFAULT_DEADLINE_DAYS = 3
TABLE = "tasks"


def _headers() -> dict:
    return {
        "apikey": settings.SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _resolve_assignee(raw) -> dict | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        email = raw.get("email")
        if email:
            return resolve_by_email(email)
        name = raw.get("name")
        return resolve_by_name(name) if name else None
    if isinstance(raw, str):
        return resolve_by_email(raw) if "@" in raw else resolve_by_name(raw)
    return None


def create_tasks_for_opted_in(payload: dict, meeting_record: dict) -> list[dict]:
    items = payload.get("action_items") or []
    if not items:
        return []

    title = payload.get("meeting_title") or payload.get("title", "")
    date = payload.get("recording_start_time", "")
    category = (meeting_record or {}).get("category", "other")
    deadline = (datetime.now(timezone.utc) + timedelta(days=DEFAULT_DEADLINE_DAYS)).isoformat()
    meeting_id = str(payload.get("recording_id"))

    rows = []
    for item in items:
        assignee = _resolve_assignee(item.get("assignee"))
        if not assignee or not assignee.get("auto_pulse_tasks"):
            continue
        timestamp = item.get("recording_timestamp")
        playback = item.get("recording_playback_url")
        notes = f"From meeting: {title} ({date})"
        if timestamp and playback:
            notes += f"\nAt {timestamp}: {playback}"
        rows.append({
            "description": (item.get("description") or "").strip(),
            "assignee": assignee["name"],
            "meeting_id": meeting_id,
            "category": category,
            "status": "in-progress",
            "priority": "medium",
            "deadline": deadline,
            "created_by": "fathom",
            "notes": notes,
        })

    if not rows:
        return []
    url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/{TABLE}"
    response = httpx.post(url, headers=_headers(), json=rows, timeout=30.0)
    response.raise_for_status()
    return response.json() or []
