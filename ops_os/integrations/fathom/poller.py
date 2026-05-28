from datetime import datetime, timedelta, timezone

import httpx
import redis

from celery_app import app
from settings import settings

from . import processor

LAST_POLLED_KEY = "fathom:last_polled_at"


def _checkpoint() -> str:
    r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    cached = r.get(LAST_POLLED_KEY)
    if cached:
        return cached
    fallback = datetime.now(timezone.utc) - timedelta(hours=settings.FATHOM_POLL_LOOKBACK_HOURS)
    return fallback.isoformat().replace("+00:00", "Z")


def _save_checkpoint(value: str) -> None:
    redis.Redis.from_url(settings.REDIS_URL, decode_responses=True).set(LAST_POLLED_KEY, value)


def _list_meetings(after_iso: str) -> list[dict]:
    headers = {"X-Api-Key": settings.FATHOM_API_KEY}
    url = f"{settings.FATHOM_API_BASE_URL}/meetings"
    items: list[dict] = []
    cursor: str | None = None
    while True:
        params = {
            "created_after": after_iso,
            "include_action_items": "true",
            "include_summary": "true",
            "include_transcript": "true",
        }
        if cursor:
            params["cursor"] = cursor
        response = httpx.get(url, headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        items.extend(data.get("items") or [])
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return items


@app.task(name="tasks.poll_fathom_recordings")
def poll_fathom_recordings() -> dict:
    if not settings.FATHOM_API_KEY:
        return {"skipped": "FATHOM_API_KEY not set"}

    started_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    after = _checkpoint()
    items = _list_meetings(after)
    for item in items:
        processor.process_fathom_recording.delay(item)
    _save_checkpoint(started_iso)
    return {
        "polled_after": after,
        "found": len(items),
        "checkpoint_advanced_to": started_iso,
    }
