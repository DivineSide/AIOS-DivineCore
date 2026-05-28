from datetime import datetime, timezone

import httpx

from settings import settings
from team import is_team_email, resolve_by_email

TRANSCRIPT_LIMIT = 90_000
TABLE = "meetings"


def _headers(prefer: str) -> dict:
    return {
        "apikey": settings.SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _resolve_owner(payload: dict) -> str:
    recorded_by = payload.get("recorded_by") or {}
    email = recorded_by.get("email") if isinstance(recorded_by, dict) else None
    member = resolve_by_email(email) if email else None
    return member["name"] if member else "unknown"


def _attendee_emails(payload: dict) -> list[str]:
    invitees = payload.get("calendar_invitees") or []
    return [i.get("email", "").lower() for i in invitees if i.get("email")]


def _split_attendees(payload: dict) -> tuple[str, str]:
    emails = _attendee_emails(payload)
    internal = [e for e in emails if is_team_email(e)]
    external = [e for e in emails if not is_team_email(e)]
    return ", ".join(internal + external), ", ".join(external)


def _summary_text(payload: dict) -> str:
    raw = payload.get("default_summary")
    if isinstance(raw, dict):
        return raw.get("markdown_formatted", "") or ""
    return raw or ""


def _transcript_text(payload: dict) -> str:
    raw = payload.get("transcript")
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, list):
        return ""
    lines = []
    for seg in raw:
        if not isinstance(seg, dict):
            lines.append(str(seg))
            continue
        speaker = seg.get("speaker") or {}
        name = speaker.get("display_name", "") if isinstance(speaker, dict) else str(speaker)
        ts = seg.get("timestamp", "")
        text = seg.get("text", "")
        lines.append(f"[{ts}] {name}: {text}".strip())
    return "\n".join(lines)


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    if len(text) <= TRANSCRIPT_LIMIT:
        return text
    return text[:TRANSCRIPT_LIMIT] + "\n\n[truncated — see transcript_url for full]"


def _duration_minutes(payload: dict) -> int:
    start = payload.get("recording_start_time")
    end = payload.get("recording_end_time")
    if not (start and end):
        return 0
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return max(0, int((e - s).total_seconds() // 60))
    except (ValueError, AttributeError):
        return 0


def _row(payload: dict, category: str) -> dict:
    attendees, external = _split_attendees(payload)
    return {
        "meeting_id": str(payload.get("recording_id")),
        "title": payload.get("meeting_title") or payload.get("title", ""),
        "date": payload.get("recording_start_time") or payload.get("scheduled_start_time"),
        "duration_min": _duration_minutes(payload),
        "owner": _resolve_owner(payload),
        "attendees": attendees,
        "external_attendees": external,
        "category": category,
        "summary": _summary_text(payload),
        "transcript": _truncate(_transcript_text(payload)),
        "transcript_url": payload.get("share_url") or payload.get("url", ""),
        "recording_url": payload.get("url", ""),
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def upsert(payload: dict, category: str) -> dict:
    row = _row(payload, category)
    url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/{TABLE}?on_conflict=meeting_id"
    response = httpx.post(
        url,
        headers=_headers("resolution=merge-duplicates,return=representation"),
        json=[row],
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return (data or [row])[0]
