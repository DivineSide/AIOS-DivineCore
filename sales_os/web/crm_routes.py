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


@router.get("/crm/api/kpi/history")
def api_kpi_history(days: int = 30) -> JSONResponse:
    try:
        return JSONResponse(supabase_writer.kpi_history(days))
    except Exception as exc:
        logger.exception("crm: kpi history failed")
        raise HTTPException(status_code=500, detail=str(exc))
