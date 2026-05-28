"""Celery tasks for the Instantly integration.

Two entry points:
- `tasks.process_instantly_reply` — invoked by the FastAPI webhook handler in
  `sales_os/web/instantly_routes.py`. Stores meaningful replies, pings Discord
  on positive ones.
- `tasks.poll_instantly_campaigns` — invoked daily by Celery Beat. Snapshots
  Instantly's campaign + step analytics into Supabase.

Webhook payload shapes vary by Instantly plan. The reply extractor below
reads from several common field names (`lead_email`, `email`, `from_email`,
etc.) and falls back to empty values rather than crashing — the full raw
payload is always stored in `outreach_replies.raw_payload` for forensics.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from celery_app import app

from . import (
    categories,
    client,
    discord_notify,
    drafter,
    gmail_client,
    intent_classifier,
    supabase_writer,
)


# ---------- reply payload extraction ----------

def _first(payload: dict, *keys: str) -> Any:
    for k in keys:
        if k in payload and payload[k] not in (None, ""):
            return payload[k]
    return None


def _nested(payload: dict, path: list[str]) -> Any:
    cur: Any = payload
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur in (None, ""):
            return None
    return cur


def _extract_first_name(payload: dict, lead_email: str) -> str | None:
    """Pull a first name from the payload, else derive from the email local part.
    Returns None if neither yields anything reasonable -- the drafter then skips
    the greeting line entirely."""
    lead = payload.get("lead") if isinstance(payload.get("lead"), dict) else {}
    name = (
        _first(payload, "first_name", "firstName", "lead_first_name")
        or lead.get("first_name")
        or lead.get("firstName")
        or lead.get("name")
    )
    if name:
        parts = str(name).split()
        if parts:
            return parts[0].strip().capitalize() or None
    if lead_email and "@" in lead_email:
        local = lead_email.split("@", 1)[0]
        cleaned = re.sub(r"[\d.\-_+]", " ", local).split()
        if cleaned:
            return cleaned[0].capitalize()
    return None


def _extract_reply(payload: dict) -> dict[str, Any]:
    lead = payload.get("lead") if isinstance(payload.get("lead"), dict) else {}
    campaign = payload.get("campaign") if isinstance(payload.get("campaign"), dict) else {}
    reply = payload.get("reply") if isinstance(payload.get("reply"), dict) else {}

    lead_email = (
        _first(payload, "lead_email", "email", "from_email", "reply_from_email")
        or lead.get("email")
        or ""
    )

    return {
        "instantly_lead_id": (
            _first(payload, "lead_id", "instantly_lead_id")
            or lead.get("id")
            or lead.get("lead_id")
        ),
        "lead_email": lead_email,
        "lead_first_name": _extract_first_name(payload, lead_email),
        "lead_company": (
            _first(payload, "company", "company_name")
            or lead.get("company")
            or lead.get("company_name")
        ),
        "campaign_id": (
            _first(payload, "campaign_id", "instantly_campaign_id")
            or campaign.get("id")
            or campaign.get("campaign_id")
        ),
        "campaign_name": (
            _first(payload, "campaign_name") or campaign.get("name")
        ),
        "step_index": (
            _first(payload, "step", "step_index", "email_position", "sequence_step")
            or reply.get("step")
            or reply.get("step_index")
        ),
        "replied_at": (
            _first(payload, "replied_at", "received_at", "timestamp", "event_timestamp")
            or reply.get("received_at")
            or datetime.now(timezone.utc).isoformat()
        ),
        "body": (
            _first(payload, "reply_text", "body", "message", "reply_body")
            or reply.get("text")
            or reply.get("body")
        ),
        "instantly_category": (
            _first(payload, "category", "lead_category", "lead_status", "interest", "ai_category")
            or lead.get("status")
            or lead.get("category")
        ),
        "reply_url": _first(payload, "reply_url", "thread_url", "url"),
    }


def _coerce_step(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@app.task(name="tasks.process_instantly_reply")
def process_instantly_reply(payload: dict) -> dict:
    """Webhook handler. Chain:

    1. Extract reply fields from Instantly's payload (best-effort across shapes).
    2. Drop if Instantly category is OOO / auto-reply (no row created).
    3. Insert base row into outreach_replies.
    4. Skip everything else if Instantly's `is_positive` is false (saves LLM calls).
    5. Classify intent via LLM (7 buckets) -> patch the row.
    6. If intent is OOO/OptOut, skip drafter + Gmail + Discord. Done.
    7. Otherwise: draft a reply (Claude in Pang's voice).
    8. Find existing Gmail thread for the lead, create Gmail draft inside it.
    9. Patch row with gmail_thread_id + gmail_draft_id + recommended_reply.
    10. Post enhanced Discord embed (intent, drafted text, Gmail link).

    Every LLM/Gmail/Discord step is wrapped in try/except -- a failure in any
    one of them won't crash the webhook handler. Errors land in the worker logs.
    """
    fields = _extract_reply(payload)
    category = fields["instantly_category"]

    if categories.is_ignored(category):
        return {"skipped": "ignored_category", "category": category}

    is_positive = categories.is_positive(category)

    reply_row = supabase_writer.insert_reply(
        instantly_lead_id=fields["instantly_lead_id"],
        lead_email=fields["lead_email"] or "unknown@unknown",
        lead_company=fields["lead_company"],
        campaign_id=fields["campaign_id"],
        step_index=_coerce_step(fields["step_index"]),
        replied_at=fields["replied_at"],
        body=fields["body"],
        instantly_category=category,
        is_positive=is_positive,
        reply_url=fields["reply_url"],
        raw_payload=payload,
    )
    reply_id = reply_row.get("id")

    if not is_positive:
        return {
            "stored": True,
            "reply_id": reply_id,
            "category": category,
            "discord": "skipped (not positive)",
        }

    # ----- classifier -----
    classification: dict[str, Any] = {"intent": "Question", "confidence": 0.0, "key_message": ""}
    try:
        classification = intent_classifier.classify(fields["body"] or "")
        if reply_id:
            supabase_writer.update_reply_with_classification(
                reply_id,
                intent=classification["intent"],
                confidence=classification["confidence"],
                key_message=classification["key_message"],
            )
    except Exception as exc:
        print(f"[instantly] classifier failed (non-fatal): {exc}", flush=True)

    intent = classification["intent"]

    if intent in drafter.SKIP_INTENTS:
        return {
            "stored": True,
            "reply_id": reply_id,
            "intent": intent,
            "discord": f"skipped ({intent})",
        }

    # ----- drafter -----
    drafted_text = ""
    try:
        drafted_text = drafter.draft(
            intent=intent,
            key_message=classification["key_message"],
            reply_body=fields["body"] or "",
            lead_first_name=fields.get("lead_first_name"),
            lead_company=fields["lead_company"],
            lead_email=fields["lead_email"] or "",
        )
    except Exception as exc:
        print(f"[instantly] drafter failed (non-fatal): {exc}", flush=True)

    # ----- Gmail draft -----
    gmail_url: str | None = None
    if drafted_text and fields["lead_email"]:
        try:
            thread_id, subject = gmail_client.find_thread_for_email(fields["lead_email"])
            draft_info = gmail_client.create_draft_reply(
                thread_id=thread_id,
                to_email=fields["lead_email"],
                subject=subject,
                body=drafted_text,
            )
            gmail_url = draft_info["gmail_url"]
            if reply_id:
                supabase_writer.update_reply_with_draft(
                    reply_id,
                    gmail_thread_id=draft_info["thread_id"],
                    gmail_draft_id=draft_info["draft_id"],
                    recommended_reply=drafted_text,
                )
        except Exception as exc:
            print(f"[instantly] gmail draft failed (non-fatal): {exc}", flush=True)

    # ----- enrich campaign context for the Discord embed -----
    positioning = None
    campaign_name = fields["campaign_name"]
    if fields["campaign_id"]:
        try:
            campaign_row = supabase_writer.fetch_campaign(fields["campaign_id"])
            if campaign_row:
                positioning = campaign_row.get("positioning") or None
                campaign_name = campaign_name or campaign_row.get("name")
        except Exception as exc:
            print(f"[instantly] fetch_campaign failed (non-fatal): {exc}", flush=True)

    # ----- Discord ping (enhanced embed) -----
    posted = False
    try:
        posted = discord_notify.post_classified_reply(
            lead_email=fields["lead_email"] or "unknown",
            lead_company=fields["lead_company"],
            campaign_name=campaign_name,
            positioning=positioning,
            intent=intent,
            confidence=classification["confidence"],
            key_message=classification["key_message"],
            body=fields["body"],
            drafted_reply=drafted_text,
            gmail_url=gmail_url,
            reply_url=fields["reply_url"],
        )
    except Exception as exc:
        print(f"[instantly] discord_notify failed (non-fatal): {exc}", flush=True)

    return {
        "stored": True,
        "reply_id": reply_id,
        "intent": intent,
        "confidence": classification["confidence"],
        "drafted": bool(drafted_text),
        "gmail_draft": bool(gmail_url),
        "discord": "posted" if posted else "skipped (no webhook)",
    }


# ---------- daily snapshot ----------

# Field names returned by Instantly's /campaigns/analytics{,/steps} endpoints.
# Verified against live payloads stored in raw_snapshot. We prefer the unique_*
# variants where they exist (e.g. unique_replies dedupes multi-replies from the
# same lead — that's the count users care about for reply-rate metrics).
# Open and bounce fields are intentionally not extracted — Instantly returns
# 0 for opens on these campaigns (no pixel tracking) and the operator has
# decided neither metric is worth surfacing.
_SENT_KEYS = ("sent", "emails_sent_count", "total_sent", "email_sent_count")
_REPLIED_KEYS = ("unique_replies", "replies", "emails_replied_count", "replied", "total_replies", "reply_count")
_UNSUB_KEYS = ("unsubscribes", "unsubscribed", "unsubscribe_count", "total_unsubscribes")


def _sum_int(blob: dict, keys: tuple[str, ...]) -> int:
    for k in keys:
        if k in blob and blob[k] is not None:
            try:
                return int(blob[k])
            except (TypeError, ValueError):
                continue
    return 0


def _campaign_name(c: dict) -> str:
    return c.get("name") or c.get("campaign_name") or "(unnamed)"


def _campaign_status(c: dict) -> str:
    raw = c.get("status")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, int):
        return f"status_{raw}"
    return ""


def _campaign_started_at(c: dict) -> str | None:
    return c.get("created_at") or c.get("started_at") or c.get("launch_date")


def _snapshot_one_campaign(campaign: dict, snapshot_date: date) -> dict:
    campaign_id = str(campaign.get("id") or campaign.get("campaign_id") or "")
    if not campaign_id:
        return {"skipped": "no campaign id"}

    supabase_writer.upsert_campaign(
        campaign_id=campaign_id,
        name=_campaign_name(campaign),
        status=_campaign_status(campaign),
        started_at=_campaign_started_at(campaign),
    )

    overall = client.get_campaign_analytics(campaign_id)
    steps = client.get_campaign_steps_analytics(campaign_id)

    metrics_rows: list[dict] = []

    if steps:
        for s in steps:
            step_index = int(s.get("step") or s.get("step_index") or s.get("position") or 1)
            supabase_writer.upsert_sequence_step(
                campaign_id=campaign_id,
                step_index=step_index,
                subject=s.get("subject"),
                body_preview=s.get("body") or s.get("body_preview"),
            )
            row = supabase_writer.upsert_daily_metrics(
                campaign_id=campaign_id,
                step_index=step_index,
                metrics_date=snapshot_date,
                emails_sent=_sum_int(s, _SENT_KEYS),
                replies=_sum_int(s, _REPLIED_KEYS),
                unsubscribes=_sum_int(s, _UNSUB_KEYS),
                raw_snapshot=s,
            )
            metrics_rows.append(row)
    else:
        # Fallback: one rolled-up row at step_index=0 when per-step analytics
        # isn't available on the plan.
        row = supabase_writer.upsert_daily_metrics(
            campaign_id=campaign_id,
            step_index=0,
            metrics_date=snapshot_date,
            emails_sent=_sum_int(overall, _SENT_KEYS),
            replies=_sum_int(overall, _REPLIED_KEYS),
            unsubscribes=_sum_int(overall, _UNSUB_KEYS),
            raw_snapshot=overall,
        )
        metrics_rows.append(row)

    return {"campaign_id": campaign_id, "rows_written": len(metrics_rows)}


@app.task(name="tasks.ping_pending_followups")
def ping_pending_followups() -> dict:
    """Daily beat task. Scans positive replies (already classified non-OOO/OptOut)
    that need a follow-up reminder ping, and posts to Discord.

    Cadence: for each positive reply, ping on day +1, +2, +3 after the reply
    landed. Capped at settings.DIVINESIDE_FOLLOWUP_MAX_PINGS (default 3) total.
    After the cap, the lead falls out of the scan window naturally.

    Stage is intentionally NOT auto-promoted. Pang updates outreach_replies.stage
    manually in Supabase Studio for leads that close or go cold.
    """
    from settings import settings

    gap_hours = 24
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=gap_hours)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    max_pings = settings.DIVINESIDE_FOLLOWUP_MAX_PINGS

    candidates = supabase_writer.fetch_replies_due_for_followup(cutoff_iso=cutoff)
    pinged = 0
    skipped = 0

    for r in candidates:
        try:
            current_count = int(r.get("follow_up_count") or 0)
            if current_count >= max_pings:
                continue
            posted = discord_notify.post_followup_reminder(
                lead_email=r.get("lead_email") or "unknown",
                lead_company=r.get("lead_company"),
                intent=r.get("intent"),
                key_message=r.get("key_message"),
                follow_up_count=current_count,
                max_pings=max_pings,
                gmail_thread_id=r.get("gmail_thread_id"),
                replied_at=r.get("replied_at"),
            )
            if posted:
                supabase_writer.mark_followup_sent(
                    r["id"],
                    now_iso=now_iso,
                    new_count=current_count + 1,
                )
                pinged += 1
            else:
                skipped += 1
        except Exception as exc:
            print(f"[instantly] follow-up ping failed for {r.get('id')}: {exc}", flush=True)
            skipped += 1

    return {
        "scanned": len(candidates),
        "pinged": pinged,
        "skipped": skipped,
    }


@app.task(name="tasks.poll_instantly_campaigns")
def poll_instantly_campaigns() -> dict:
    from settings import settings

    if not settings.INSTANTLY_API_KEY:
        return {"skipped": "INSTANTLY_API_KEY not set"}

    snapshot_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    campaigns = client.list_campaigns()
    results: list[dict] = []
    for c in campaigns:
        try:
            results.append(_snapshot_one_campaign(c, snapshot_date))
        except Exception as exc:
            print(f"[instantly] snapshot failed for {c.get('id')}: {exc}", flush=True)
            results.append({"campaign_id": c.get("id"), "error": str(exc)})
    return {
        "snapshot_date": snapshot_date.isoformat(),
        "campaigns_seen": len(campaigns),
        "results": results,
    }
