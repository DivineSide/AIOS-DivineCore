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


def kpi_history(days: int = 30) -> list[dict[str, Any]]:
    url = (
        f"{_rest_base()}/{KPI_TABLE}"
        f"?select=date,metric,value&order=date.desc&limit={days * 40}"
    )
    r = httpx.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return r.json() or []
