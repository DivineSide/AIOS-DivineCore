"""Thin httpx wrapper around Instantly's REST API.

Endpoint paths and response shapes mirror Instantly's v2 public API as
documented at the time of writing. Verify against the live account on first
poll — the daily snapshot (`poll_instantly_campaigns`) writes the full raw
response to `outreach_daily_step_metrics.raw_snapshot` so any drift can be
inspected in Supabase.
"""

from __future__ import annotations

from typing import Any

import httpx

from settings import settings


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.INSTANTLY_API_KEY}",
        "Content-Type": "application/json",
    }


def _base() -> str:
    return settings.INSTANTLY_API_BASE_URL.rstrip("/")


def list_campaigns() -> list[dict[str, Any]]:
    """Return all campaigns visible to this API key.

    Paginates through Instantly's cursor-style response. Returns the raw
    `items` list from each page concatenated.
    """
    url = f"{_base()}/api/v2/campaigns"
    items: list[dict] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["starting_after"] = cursor
        response = httpx.get(url, headers=_headers(), params=params, timeout=30.0)
        response.raise_for_status()
        data = response.json() or {}
        page = data.get("items") or data.get("data") or []
        items.extend(page)
        cursor = data.get("next_starting_after") or data.get("next_cursor")
        if not cursor or not page:
            break
    return items


def get_campaign(campaign_id: str) -> dict[str, Any]:
    url = f"{_base()}/api/v2/campaigns/{campaign_id}"
    response = httpx.get(url, headers=_headers(), timeout=30.0)
    response.raise_for_status()
    return response.json() or {}


def get_campaign_analytics(campaign_id: str) -> dict[str, Any]:
    """Cumulative campaign-level analytics. We snapshot this once per day
    and let the dashboard compute deltas in SQL.
    """
    url = f"{_base()}/api/v2/campaigns/analytics"
    response = httpx.get(
        url,
        headers=_headers(),
        params={"campaign_id": campaign_id},
        timeout=30.0,
    )
    response.raise_for_status()
    body = response.json()
    if isinstance(body, list):
        return body[0] if body else {}
    return body or {}


def get_campaign_steps_analytics(campaign_id: str) -> list[dict[str, Any]]:
    """Per-sequence-step analytics breakdown (initial vs follow-ups).

    Some Instantly plans expose this at `/api/v2/campaigns/analytics/steps`.
    Returns an empty list if the endpoint isn't available — the daily metrics
    table will still get a single step_index=0 row per campaign in that case.
    """
    url = f"{_base()}/api/v2/campaigns/analytics/steps"
    try:
        response = httpx.get(
            url,
            headers=_headers(),
            params={"campaign_id": campaign_id},
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (404, 405):
            return []
        raise
    body = response.json()
    if isinstance(body, list):
        return body
    return body.get("items") or body.get("data") or []
