"""PostgREST CRUD for the LinkedIn pipeline (li_prospects). Same pattern as
sales_os/crm/supabase_writer. Secret key server-side only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from settings import settings

TABLE = "li_prospects"

WRITABLE = {"name", "linkedin_url", "tier", "stage", "replied", "next_action_date", "notes", "source"}


def _headers(prefer: str | None = None) -> dict[str, str]:
    h = {
        "apikey": settings.SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _rest_base() -> str:
    return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1"


def _clean(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k in WRITABLE}


def list_prospects() -> list[dict[str, Any]]:
    url = f"{_rest_base()}/{TABLE}?select=*&order=next_action_date.asc.nullslast,created_at.desc"
    r = httpx.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return r.json() or []


def create_prospect(body: dict[str, Any]) -> dict[str, Any]:
    row = _clean(body)
    row.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    url = f"{_rest_base()}/{TABLE}"
    r = httpx.post(url, headers=_headers("return=representation"), json=[row], timeout=30.0)
    r.raise_for_status()
    return (r.json() or [row])[0]


def update_prospect(prospect_id: str, body: dict[str, Any]) -> dict[str, Any]:
    row = _clean(body)
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    url = f"{_rest_base()}/{TABLE}?id=eq.{prospect_id}"
    r = httpx.patch(url, headers=_headers("return=representation"), json=row, timeout=30.0)
    r.raise_for_status()
    data = r.json()
    return (data or [row])[0]


def delete_prospect(prospect_id: str) -> None:
    url = f"{_rest_base()}/{TABLE}?id=eq.{prospect_id}"
    r = httpx.delete(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()


def existing_urls() -> set[str]:
    url = f"{_rest_base()}/{TABLE}?select=linkedin_url&linkedin_url=neq."
    r = httpx.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return {row["linkedin_url"] for row in (r.json() or []) if row.get("linkedin_url")}


def bulk_insert(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    payload = [{**_clean(r), "updated_at": now} for r in rows]
    url = f"{_rest_base()}/{TABLE}"
    inserted = 0
    for i in range(0, len(payload), 500):
        resp = httpx.post(url, headers=_headers("return=representation"), json=payload[i:i + 500], timeout=60.0)
        resp.raise_for_status()
        inserted += len(resp.json() or [])
    return inserted
