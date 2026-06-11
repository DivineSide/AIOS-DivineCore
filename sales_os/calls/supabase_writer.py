"""PostgREST writers/readers for the Cold Call Dialer tables.

Same auth + REST pattern as sales_os/crm/supabase_writer.py. Secret key is
server-side only, so /dialer can sit behind Traefik basic auth and keep lead
PII out of the public client. Touches ONLY call_prospects / call_logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from settings import settings

PROSPECTS_TABLE = "call_prospects"
LOGS_TABLE = "call_logs"

PROSPECT_WRITABLE = {
    "name", "business_name", "phone", "raw_phone", "area_code", "time_zone",
    "calling_block", "email", "website", "city", "state", "status",
    "next_follow_up_at", "source", "needs_review",
}


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
    return {k: v for k, v in body.items() if k in PROSPECT_WRITABLE}


# ---------- prospects ----------

def list_prospects(block: str | None = None, status: str | None = None,
                   due_cutoff_iso: str | None = None) -> list[dict[str, Any]]:
    parts = [
        "select=*,call_logs(id,disposition,note,attempted_at)",
        "order=next_follow_up_at.asc.nullslast,created_at.desc",
    ]
    if block:
        parts.append(f"calling_block=eq.{block}")
    if status:
        parts.append(f"status=eq.{status}")
    if due_cutoff_iso:
        from urllib.parse import quote
        parts.append(f"next_follow_up_at=lte.{quote(due_cutoff_iso, safe='')}")
    url = f"{_rest_base()}/{PROSPECTS_TABLE}?" + "&".join(parts)
    r = httpx.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return r.json() or []


def existing_phones() -> set[str]:
    url = f"{_rest_base()}/{PROSPECTS_TABLE}?select=phone&phone=neq."
    r = httpx.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return {row["phone"] for row in (r.json() or []) if row.get("phone")}


def bulk_insert_prospects(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    payload = [{**_clean(r), "updated_at": now} for r in rows]
    url = f"{_rest_base()}/{PROSPECTS_TABLE}"
    inserted = 0
    for i in range(0, len(payload), 500):
        chunk = payload[i:i + 500]
        resp = httpx.post(url, headers=_headers("return=representation"), json=chunk, timeout=60.0)
        resp.raise_for_status()
        inserted += len(resp.json() or [])
    return inserted


def create_prospect(body: dict[str, Any]) -> dict[str, Any]:
    row = _clean(body)
    row.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    url = f"{_rest_base()}/{PROSPECTS_TABLE}"
    r = httpx.post(url, headers=_headers("return=representation"), json=[row], timeout=30.0)
    r.raise_for_status()
    return (r.json() or [row])[0]


def update_prospect(prospect_id: str, body: dict[str, Any]) -> dict[str, Any]:
    row = _clean(body)
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    url = f"{_rest_base()}/{PROSPECTS_TABLE}?id=eq.{prospect_id}"
    r = httpx.patch(url, headers=_headers("return=representation"), json=row, timeout=30.0)
    r.raise_for_status()
    return (r.json() or [row])[0]


def delete_prospect(prospect_id: str) -> None:
    url = f"{_rest_base()}/{PROSPECTS_TABLE}?id=eq.{prospect_id}"
    r = httpx.delete(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()


# ---------- call logs ----------

def add_log(prospect_id: str, disposition: str, note: str) -> dict[str, Any]:
    row = {
        "prospect_id": prospect_id,
        "disposition": disposition or "",
        "note": (note or "")[:5000],
        "attempted_at": datetime.now(timezone.utc).isoformat(),
    }
    url = f"{_rest_base()}/{LOGS_TABLE}"
    r = httpx.post(url, headers=_headers("return=representation"), json=[row], timeout=30.0)
    r.raise_for_status()
    return (r.json() or [row])[0]
