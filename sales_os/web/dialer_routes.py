"""Cold Call Dialer API. The UI is a tab inside the /crm single-page app
(sales_os/web/templates/crm.html); this module only serves the JSON API, all
under the /crm/api/dialer/* prefix so nothing lives at a separate /dialer URL.

POST /crm/api/dialer/import               -> CSV import (multipart: file + mapping)
GET  /crm/api/dialer/prospects            -> list (?block= &status= &due=today)
POST /crm/api/dialer/prospects            -> create one manually
PATCH/DELETE /crm/api/dialer/prospects/{id}
POST /crm/api/dialer/prospects/{id}/log   -> add a call_log (disposition + note),
                                             also sets prospect.status

All routes sit behind the same Traefik basic auth as /crm and /upwork.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from sales_os.calls import supabase_writer as writer
from sales_os.calls.phones import parse_phone

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dialer"], prefix="/crm/api/dialer")

VALID_STATUS = {
    "new", "dialed", "no_answer", "voicemail", "not_interested",
    "callback", "booked", "wrong_number", "do_not_call",
}


# ---------- CSV import ----------

@router.post("/import")
async def api_import(file: UploadFile = File(...), mapping: str = Form(...)) -> JSONResponse:
    try:
        cmap = json.loads(mapping)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="mapping must be valid JSON")
    if not cmap.get("phone") and not cmap.get("name"):
        raise HTTPException(status_code=400, detail="map at least a phone or name column")

    text = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    existing = writer.existing_phones()
    seen: set[str] = set()
    to_insert: list[dict] = []
    total = dupes = review = 0

    for raw in reader:
        total += 1

        def g(key: str) -> str:
            col = cmap.get(key)
            return (raw.get(col) or "").strip() if col else ""

        name, phone_raw = g("name"), g("phone")
        if not name and not phone_raw:
            continue

        rec = {
            "name": name or "(no name)",
            "business_name": g("business"),
            "raw_phone": phone_raw,
            "email": g("email"),
            "website": g("website"),
            "city": g("city"),
            "state": g("state"),
            "source": "csv",
            "status": "new",
        }
        parsed = parse_phone(phone_raw)
        if parsed:
            if parsed["phone"] in existing or parsed["phone"] in seen:
                dupes += 1
                continue
            seen.add(parsed["phone"])
            rec.update(parsed)
        else:
            rec["needs_review"] = True
            review += 1
        to_insert.append(rec)

    try:
        imported = writer.bulk_insert_prospects(to_insert)
    except Exception as exc:
        logger.exception("dialer: import insert failed")
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse({
        "total": total, "imported": imported,
        "duplicates": dupes, "needs_review": review,
    })


# ---------- prospects ----------

@router.get("/prospects")
def api_list(block: str | None = None, status: str | None = None, due: str | None = None) -> JSONResponse:
    cutoff = None
    if due == "today":
        now = datetime.now(timezone.utc)
        cutoff = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
    try:
        return JSONResponse(writer.list_prospects(block=block, status=status, due_cutoff_iso=cutoff))
    except Exception as exc:
        logger.exception("dialer: list failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/prospects")
def api_create(body: dict = Body(...)) -> JSONResponse:
    if not (body.get("name") or "").strip() and not (body.get("phone") or "").strip():
        raise HTTPException(status_code=400, detail="name or phone is required")
    body.setdefault("name", "(no name)")
    body.setdefault("source", "manual")
    body.setdefault("status", "new")
    raw_phone = body.get("phone") or body.get("raw_phone") or ""
    if raw_phone:
        body["raw_phone"] = raw_phone
        parsed = parse_phone(raw_phone)
        if parsed:
            body.update(parsed)
        else:
            body["phone"] = ""
            body["needs_review"] = True
    try:
        return JSONResponse(writer.create_prospect(body), status_code=201)
    except Exception as exc:
        logger.exception("dialer: create failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/prospects/{prospect_id}")
def api_update(prospect_id: str, body: dict = Body(...)) -> JSONResponse:
    if "status" in body and body["status"] not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"invalid status: {body['status']}")
    try:
        return JSONResponse(writer.update_prospect(prospect_id, body))
    except Exception as exc:
        logger.exception("dialer: update failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/prospects/{prospect_id}")
def api_delete(prospect_id: str) -> JSONResponse:
    try:
        writer.delete_prospect(prospect_id)
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.exception("dialer: delete failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/prospects/{prospect_id}/log")
def api_log(prospect_id: str, body: dict = Body(...)) -> JSONResponse:
    disposition = (body.get("disposition") or "").strip()
    if disposition and disposition not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"invalid disposition: {disposition}")
    note = body.get("note") or ""
    try:
        log = writer.add_log(prospect_id, disposition, note)
        if disposition:
            writer.update_prospect(prospect_id, {"status": disposition})
        return JSONResponse(log, status_code=201)
    except Exception as exc:
        logger.exception("dialer: log failed")
        raise HTTPException(status_code=500, detail=str(exc))
