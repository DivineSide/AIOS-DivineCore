"""PostgREST writers/readers for the CRM dashboard tables.

Mirrors the auth + REST pattern in
sales_os/integrations/instantly/supabase_writer.py. The secret key is used
server-side only (never shipped to the browser), so the /crm page can sit
behind Traefik basic auth and still keep lead PII out of the public client.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from settings import settings

PROSPECTS_TABLE = "crm_prospects"
KPI_TABLE = "kpi_daily"
CONTENT_TABLE = "content_posts"

# Columns the content import is allowed to write (mirrors the tracker CSV).
CONTENT_WRITABLE = {
    "post_id", "platform", "posted_at", "url", "post_type", "framework",
    "funnel_stage", "topic", "format", "differentiator", "hook", "closing",
    "content", "views", "likes", "comments", "reposts", "bookmarks", "notes",
}
_CONTENT_INT_COLS = {"views", "likes", "comments", "reposts", "bookmarks"}

# Columns a client request is allowed to write. Anything else is ignored so a
# malformed/hostile body can't set arbitrary fields.
PROSPECT_WRITABLE = {
    "name", "company", "source", "temp", "stage", "email", "phone",
    "linkedin_url", "next_touch_date", "last_touch_at", "touch_count", "notes",
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

def list_prospects() -> list[dict[str, Any]]:
    url = (
        f"{_rest_base()}/{PROSPECTS_TABLE}"
        "?select=*&order=next_touch_date.asc.nullslast,created_at.desc"
    )
    r = httpx.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return r.json() or []


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
    data = r.json()
    return (data or [row])[0]


def delete_prospect(prospect_id: str) -> None:
    url = f"{_rest_base()}/{PROSPECTS_TABLE}?id=eq.{prospect_id}"
    r = httpx.delete(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()


# ---------- kpi ----------

def get_kpi_for_date(day: str) -> list[dict[str, Any]]:
    url = f"{_rest_base()}/{KPI_TABLE}?date=eq.{day}&select=metric,value"
    r = httpx.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return r.json() or []


def set_kpi(day: str, metric: str, value: int) -> dict[str, Any]:
    """Upsert a single (date, metric) cell to an absolute value."""
    row = {
        "date": day,
        "metric": metric,
        "value": max(0, int(value)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    url = f"{_rest_base()}/{KPI_TABLE}?on_conflict=date,metric"
    r = httpx.post(
        url,
        headers=_headers("resolution=merge-duplicates,return=representation"),
        json=[row],
        timeout=30.0,
    )
    r.raise_for_status()
    return (r.json() or [row])[0]


def bump_kpi(day: str, metric: str, delta: int) -> dict[str, Any]:
    """Atomically increment one (date, metric) cell by delta via the kpi_bump
    Postgres function. Used by cross-module auto-logging (e.g. a LinkedIn comment
    ticks the comments KPI, a connection request ticks conn_sent).

    The increment runs in a single SQL statement under a row lock, so rapid
    concurrent bumps (clicking many "connection request sent" buttons fast, each
    a fire-and-forget request) all land. The old read-then-set version lost
    updates whenever two requests read the same value before either wrote back.
    """
    url = f"{_rest_base()}/rpc/kpi_bump"
    r = httpx.post(
        url,
        headers=_headers(),
        json={"p_date": day, "p_metric": metric, "p_delta": int(delta)},
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    return data[0] if isinstance(data, list) else data


def bulk_set_kpi(rows: list[dict[str, Any]]) -> int:
    """Upsert many (date, metric, value) cells in chunks. Used by the
    old-tracker import. merge-duplicates so a re-import overwrites, not dupes.
    """
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    payload = [
        {"date": r["date"], "metric": r["metric"], "value": max(0, int(r["value"])), "updated_at": now}
        for r in rows
    ]
    url = f"{_rest_base()}/{KPI_TABLE}?on_conflict=date,metric"
    for i in range(0, len(payload), 500):
        chunk = payload[i:i + 500]
        resp = httpx.post(
            url,
            headers=_headers("resolution=merge-duplicates,return=minimal"),
            json=chunk,
            timeout=60.0,
        )
        resp.raise_for_status()
    return len(payload)


# ---------- content posts ----------

def list_content_posts() -> list[dict[str, Any]]:
    url = (
        f"{_rest_base()}/{CONTENT_TABLE}"
        "?select=*&order=posted_at.desc.nullslast"
    )
    r = httpx.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return r.json() or []


def _clean_content(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k not in CONTENT_WRITABLE:
            continue
        if k in _CONTENT_INT_COLS:
            # blank / non-numeric -> NULL so "no impressions yet" stays distinct from 0.
            s = str(v).strip().replace(",", "") if v is not None else ""
            out[k] = int(float(s)) if s else None
        else:
            out[k] = v
    return out


def bulk_upsert_content_posts(rows: list[dict[str, Any]]) -> int:
    """Upsert many posts by post_id (merge-duplicates, so re-syncing the CSV
    overwrites metrics instead of duplicating). Used by the tracker -> CRM sync."""
    payload = [_clean_content(r) for r in rows if (r.get("post_id") or "").strip()]
    if not payload:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    for row in payload:
        row["updated_at"] = now
    url = f"{_rest_base()}/{CONTENT_TABLE}?on_conflict=post_id"
    for i in range(0, len(payload), 500):
        chunk = payload[i:i + 500]
        resp = httpx.post(
            url,
            headers=_headers("resolution=merge-duplicates,return=minimal"),
            json=chunk,
            timeout=60.0,
        )
        resp.raise_for_status()
    return len(payload)


def kpi_history(days: int = 30) -> list[dict[str, Any]]:
    url = (
        f"{_rest_base()}/{KPI_TABLE}"
        f"?select=date,metric,value&order=date.desc&limit={days * 40}"
    )
    r = httpx.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return r.json() or []
