"""LinkedIn engage-first pipeline API. UI is a tab in the /crm page.

GET  /crm/api/li/prospects        -> list
POST /crm/api/li/prospects        -> create
PATCH/DELETE /crm/api/li/prospects/{id}

Behind the same Traefik basic auth as /crm.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

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

# §14 DUE offsets: days from when a stage was entered until its action is due.
_DUE = {"commented": 2, "accepted": 0, "first_msg": 3, "loom_sent": 7, "engaged": 30}


def _add_days(ymd: str | None, n: int) -> str | None:
    if not ymd:
        return None
    try:
        return (date.fromisoformat(ymd[:10]) + timedelta(days=n)).isoformat()
    except ValueError:
        return None


def _stage_date(history: list | None, stage: str) -> str | None:
    d = None
    for h in history or []:
        if isinstance(h, dict) and h.get("stage") == stage:
            d = h.get("date")
    return d


def _name_from_url(url: str) -> str:
    """Local tracker prospects are added by URL with no name. Derive a readable
    name from the /in/<slug>, dropping a trailing LinkedIn id token."""
    if not url:
        return ""
    m = re.search(r"/in/([^/?#]+)", url)
    if not m:
        return ""
    parts = [p for p in m.group(1).split("-") if p]
    if len(parts) > 1 and re.fullmatch(r"[0-9a-f]{6,}", parts[-1] or ""):
        parts = parts[:-1]
    return " ".join(parts).replace("_", " ").title()


def _next_action_date(p: dict) -> str | None:
    """Reconstruct the due date the local tracker would have shown, from the
    prospect's stage + history. replied stops the silence cadence."""
    stage = p.get("stage")
    replied = bool(p.get("replied"))
    hist = p.get("history")
    if stage == "commented":
        return _add_days(_stage_date(hist, "commented"), 2)
    if stage == "accepted":
        return _stage_date(hist, "accepted")
    if stage == "first_msg" and not replied:
        return _add_days(_stage_date(hist, "first_msg"), 3)
    if stage == "loom_sent" and not replied:
        return _add_days(_stage_date(hist, "loom_sent"), 7)
    if stage == "engaged" and not replied:
        return _add_days(_stage_date(hist, "engaged"), 30)
    return None


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


@router.post("/import")
def api_import(body: dict = Body(...)) -> JSONResponse:
    """Import the local tracker backup's `prospects` array into li_prospects.
    Maps url->linkedin_url, keeps stage/tier/replied/notes, reconstructs
    next_action_date from each prospect's history, dedupes on linkedin_url.
    """
    items = body.get("prospects") or []
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="prospects must be a list")

    try:
        existing = writer.existing_urls()
    except Exception as exc:
        logger.exception("li: import preflight failed")
        raise HTTPException(status_code=500, detail=str(exc))

    seen: set[str] = set()
    rows: list[dict] = []
    dupes = skipped = 0

    for p in items:
        if not isinstance(p, dict):
            skipped += 1
            continue
        url = (p.get("url") or "").strip()
        name = (p.get("name") or "").strip() or _name_from_url(url)
        if not name and not url:
            skipped += 1
            continue
        if url and (url in existing or url in seen):
            dupes += 1
            continue
        if url:
            seen.add(url)
        if not name:
            name = "(no name)"
        stage = p.get("stage") if p.get("stage") in VALID_STAGE else "commented"
        tier = p.get("tier") if p.get("tier") in VALID_TIER else "A"
        rows.append({
            "name": name,
            "linkedin_url": url,
            "tier": tier,
            "stage": stage,
            "replied": bool(p.get("replied")),
            "notes": p.get("notes") or "",
            "next_action_date": _next_action_date(p),
            "source": "import",
        })

    try:
        imported = writer.bulk_insert(rows)
    except Exception as exc:
        logger.exception("li: import insert failed")
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse({
        "imported": imported, "duplicates": dupes,
        "skipped": skipped, "total": len(items),
    })
