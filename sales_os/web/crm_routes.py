"""CRM + KPI dashboard for the positive-reply pipeline.

GET  /crm                       -> the single-page dashboard (sidebar: KPI + Leads).
GET  /crm/api/prospects         -> list all prospects.
POST /crm/api/prospects         -> create a prospect.
PATCH/DELETE /crm/api/prospects/{id}
GET  /crm/api/kpi?date=YYYY-MM-DD   -> {metric: value} for that day.
POST /crm/api/kpi               -> set one (date, metric) cell to an absolute value.
GET  /crm/api/kpi/history?days=30   -> recent daily rows for long-term tracking.

All /crm* routes sit behind the same Traefik basic auth as /upwork and
/outreach (Host-level middleware), so lead PII is never publicly exposed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from sales_os.crm import supabase_writer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["crm"])

_INDEX = Path(__file__).resolve().parent / "templates" / "crm.html"


@router.get("/crm", response_class=HTMLResponse)
def crm_page() -> HTMLResponse:
    return HTMLResponse(_INDEX.read_text(encoding="utf-8"))


# ---------- prospects ----------

@router.get("/crm/api/prospects")
def api_list_prospects() -> JSONResponse:
    try:
        return JSONResponse(supabase_writer.list_prospects())
    except Exception as exc:
        logger.exception("crm: list prospects failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/crm/api/prospects")
def api_create_prospect(body: dict = Body(...)) -> JSONResponse:
    if not (body.get("name") or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    try:
        return JSONResponse(supabase_writer.create_prospect(body), status_code=201)
    except Exception as exc:
        logger.exception("crm: create prospect failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/crm/api/prospects/{prospect_id}")
def api_update_prospect(prospect_id: str, body: dict = Body(...)) -> JSONResponse:
    try:
        return JSONResponse(supabase_writer.update_prospect(prospect_id, body))
    except Exception as exc:
        logger.exception("crm: update prospect failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/crm/api/prospects/{prospect_id}")
def api_delete_prospect(prospect_id: str) -> JSONResponse:
    try:
        supabase_writer.delete_prospect(prospect_id)
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.exception("crm: delete prospect failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------- kpi ----------

@router.get("/crm/api/kpi")
def api_get_kpi(date: str) -> JSONResponse:
    try:
        rows = supabase_writer.get_kpi_for_date(date)
        return JSONResponse({r["metric"]: r["value"] for r in rows})
    except Exception as exc:
        logger.exception("crm: get kpi failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/crm/api/kpi")
def api_set_kpi(body: dict = Body(...)) -> JSONResponse:
    day = body.get("date")
    metric = body.get("metric")
    value = body.get("value")
    if not day or not metric or value is None:
        raise HTTPException(status_code=400, detail="date, metric, value are required")
    try:
        return JSONResponse(supabase_writer.set_kpi(day, metric, int(value)))
    except Exception as exc:
        logger.exception("crm: set kpi failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/crm/api/kpi/bump")
def api_bump_kpi(body: dict = Body(...)) -> JSONResponse:
    day = body.get("date")
    metric = body.get("metric")
    delta = int(body.get("delta", 1))
    if not day or not metric:
        raise HTTPException(status_code=400, detail="date and metric are required")
    try:
        return JSONResponse(supabase_writer.bump_kpi(day, metric, delta))
    except Exception as exc:
        logger.exception("crm: bump kpi failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/crm/api/kpi/history")
def api_kpi_history(days: int = 30) -> JSONResponse:
    try:
        return JSONResponse(supabase_writer.kpi_history(days))
    except Exception as exc:
        logger.exception("crm: kpi history failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/crm/api/content")
def api_list_content() -> JSONResponse:
    """All tracked posts, newest first — the Content dashboard computes its
    views (this-week plan, mix, top posts/hooks, reach buckets) client-side."""
    try:
        return JSONResponse(supabase_writer.list_content_posts())
    except Exception as exc:
        logger.exception("crm: list content failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/crm/api/content/import")
def api_import_content(body: dict = Body(...)) -> JSONResponse:
    """Upsert posts synced up from tools/social-tracker/posts.csv. Accepts
    {posts: [ {post_id, ...} ]} and merges by post_id (re-sync overwrites)."""
    posts = body.get("posts") or []
    if not isinstance(posts, list):
        raise HTTPException(status_code=400, detail="posts must be a list")
    try:
        n = supabase_writer.bulk_upsert_content_posts(posts)
        return JSONResponse({"upserted": n})
    except Exception as exc:
        logger.exception("crm: content import failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/crm/api/import")
def api_import(body: dict = Body(...)) -> JSONResponse:
    """Import the old local-tracker backup. Accepts {counts: {date: {metric: value}}}
    and upserts every cell into kpi_daily. Prospects are a different (cold) pipeline
    and are intentionally not imported here.
    """
    counts = body.get("counts") or {}
    rows: list[dict] = []
    for day, metrics in counts.items():
        if not isinstance(metrics, dict):
            continue
        for metric, value in metrics.items():
            try:
                v = int(value)
            except (TypeError, ValueError):
                continue
            rows.append({"date": str(day), "metric": str(metric), "value": v})
    try:
        n = supabase_writer.bulk_set_kpi(rows)
        return JSONResponse({"cells": n})
    except Exception as exc:
        logger.exception("crm: import failed")
        raise HTTPException(status_code=500, detail=str(exc))
