"""Instantly webhook ingress + outreach reporting dashboard.

POST /instantly/webhook       -> validate shared secret, enqueue reply task, return 202.
GET  /outreach                -> campaign list with positioning + lifetime metrics.
GET  /outreach/{campaign_id}  -> per-campaign detail: per-step metrics, recent replies.

The webhook route is reachable without basicauth (Traefik router split). The
GET /outreach* views sit behind the same basicauth as /upwork.
"""

from __future__ import annotations

import hmac
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from celery import Celery
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from sales_os.integrations.instantly import supabase_writer
from settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["instantly"])

_celery = Celery("api", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


# ---------- webhook ingress ----------

@router.post("/instantly/webhook")
async def instantly_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> JSONResponse:
    expected = settings.INSTANTLY_WEBHOOK_SECRET
    if not expected:
        logger.error("instantly: INSTANTLY_WEBHOOK_SECRET not set; refusing webhook")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        payload = await request.json()
    except Exception as exc:
        logger.exception("instantly: invalid JSON body")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook body must be a JSON object")

    async_result = _celery.send_task("tasks.process_instantly_reply", args=[payload])
    return JSONResponse({"task_id": async_result.id}, status_code=202)


# ---------- dashboard ----------

def _safe_div(num: float, denom: float) -> float:
    return (num / denom) if denom else 0.0


def _aggregate_lifetime(metrics_rows: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = {
        "emails_sent": 0,
        "replies": 0,
        "unsubscribes": 0,
    }
    for r in metrics_rows or []:
        for k in totals:
            totals[k] += int(r.get(k) or 0)
    return totals


@router.get("/outreach", response_class=HTMLResponse)
def outreach_list(request: Request):
    try:
        campaigns = supabase_writer.fetch_campaigns_with_metrics()
    except Exception as exc:
        logger.exception("outreach: list query failed")
        return _templates.TemplateResponse(
            "outreach_list.html",
            {"request": request, "campaigns": [], "error": str(exc)},
            status_code=500,
        )

    rows: list[dict] = []
    for c in campaigns:
        metrics_rows = c.get("outreach_daily_step_metrics") or []
        totals = _aggregate_lifetime(metrics_rows)
        sent = totals["emails_sent"]
        replies = totals["replies"]
        rows.append({
            "id": c.get("id"),
            "name": c.get("name") or "(unnamed)",
            "positioning": c.get("positioning") or "",
            "status": c.get("status") or "",
            "started_at": c.get("started_at"),
            "emails_sent": sent,
            "replies": replies,
            "unsubscribes": totals["unsubscribes"],
            "reply_rate": _safe_div(replies, sent),
        })

    return _templates.TemplateResponse(
        "outreach_list.html",
        {"request": request, "campaigns": rows, "error": None},
    )


@router.get("/outreach/{campaign_id}", response_class=HTMLResponse)
def outreach_detail(request: Request, campaign_id: str):
    try:
        campaign = supabase_writer.fetch_campaign(campaign_id)
        if not campaign:
            return _templates.TemplateResponse(
                "outreach_detail.html",
                {"request": request, "error": f"Campaign not found: {campaign_id}"},
                status_code=404,
            )
        steps = supabase_writer.fetch_steps(campaign_id)
        metrics_rows = supabase_writer.fetch_step_metrics(campaign_id, days=30)
        replies = supabase_writer.fetch_recent_replies(campaign_id, limit=50)
    except Exception as exc:
        logger.exception("outreach: detail query failed")
        return _templates.TemplateResponse(
            "outreach_detail.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )

    # Per-step lifetime totals (sum across all dates).
    per_step: dict[int, dict[str, Any]] = defaultdict(lambda: {
        "emails_sent": 0, "replies": 0, "unsubscribes": 0,
    })
    for r in metrics_rows:
        s = int(r.get("step_index") or 0)
        for k in per_step[s]:
            per_step[s][k] += int(r.get(k) or 0)

    # Reply-category breakdown from the replies table (more authoritative for
    # positive/negative/etc. than analytics, which only knows "replied").
    category_totals: dict[str, int] = defaultdict(int)
    positive_replies = 0
    for rep in replies:
        cat = (rep.get("instantly_category") or "uncategorized").strip() or "uncategorized"
        category_totals[cat] += 1
        if rep.get("is_positive"):
            positive_replies += 1

    step_rows = []
    for step in sorted(per_step.keys()):
        m = per_step[step]
        sent = m["emails_sent"]
        replies_count = m["replies"]
        step_rows.append({
            "step_index": step,
            "subject": next((s.get("subject") for s in steps if int(s.get("step_index") or 0) == step), ""),
            **m,
            "reply_rate": _safe_div(replies_count, sent),
        })

    lifetime = _aggregate_lifetime(metrics_rows)

    # Daily totals for last 30 days, summing across steps for the date column.
    daily: dict[str, dict[str, int]] = defaultdict(lambda: {
        "emails_sent": 0, "replies": 0, "unsubscribes": 0,
    })
    for r in metrics_rows:
        d = r.get("date") or ""
        for k in daily[d]:
            daily[d][k] += int(r.get(k) or 0)
    daily_rows = [{"date": k, **v} for k, v in sorted(daily.items(), reverse=True)]

    return _templates.TemplateResponse(
        "outreach_detail.html",
        {
            "request": request,
            "campaign": campaign,
            "lifetime": lifetime,
            "lifetime_reply_rate": _safe_div(lifetime["replies"], lifetime["emails_sent"]),
            "lifetime_positive_rate": _safe_div(positive_replies, lifetime["emails_sent"]),
            "positive_replies": positive_replies,
            "category_totals": dict(category_totals),
            "step_rows": step_rows,
            "daily_rows": daily_rows[:30],
            "replies": replies,
            "error": None,
        },
    )
