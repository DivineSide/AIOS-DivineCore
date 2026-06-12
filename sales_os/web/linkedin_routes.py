"""LinkedIn engage-first pipeline API. UI is a tab in the /crm page.

GET  /crm/api/li/prospects        -> list
POST /crm/api/li/prospects        -> create
PATCH/DELETE /crm/api/li/prospects/{id}

Behind the same Traefik basic auth as /crm.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from sales_os.linkedin import supabase_writer as writer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["linkedin"], prefix="/crm/api/li")

VALID_STAGE = {
    "commented", "connect_sent", "accepted", "first_msg",
    "loom_sent", "engaged", "in_convo", "won", "dead",
}
VALID_TIER = {"A", "B", "C"}


@router.get("/prospects")
def api_list() -> JSONResponse:
    try:
        return JSONResponse(writer.list_prospects())
    except Exception as exc:
        logger.exception("li: list failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/prospects")
def api_create(body: dict = Body(...)) -> JSONResponse:
    if not (body.get("name") or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if body.get("tier") and body["tier"] not in VALID_TIER:
        raise HTTPException(status_code=400, detail=f"invalid tier: {body['tier']}")
    if body.get("stage") and body["stage"] not in VALID_STAGE:
        raise HTTPException(status_code=400, detail=f"invalid stage: {body['stage']}")
    try:
        return JSONResponse(writer.create_prospect(body), status_code=201)
    except Exception as exc:
        logger.exception("li: create failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/prospects/{prospect_id}")
def api_update(prospect_id: str, body: dict = Body(...)) -> JSONResponse:
    if body.get("stage") and body["stage"] not in VALID_STAGE:
        raise HTTPException(status_code=400, detail=f"invalid stage: {body['stage']}")
    if body.get("tier") and body["tier"] not in VALID_TIER:
        raise HTTPException(status_code=400, detail=f"invalid tier: {body['tier']}")
    try:
        return JSONResponse(writer.update_prospect(prospect_id, body))
    except Exception as exc:
        logger.exception("li: update failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/prospects/{prospect_id}")
def api_delete(prospect_id: str) -> JSONResponse:
    try:
        writer.delete_prospect(prospect_id)
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.exception("li: delete failed")
        raise HTTPException(status_code=500, detail=str(exc))
