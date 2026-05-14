"""Celery task entry point for the Upwork pipeline."""

import logging
from datetime import datetime, timezone

from celery_app import app

from . import config, google_client, llm

logger = logging.getLogger(__name__)


@app.task(name="tasks.upwork_generate_proposal")
def upwork_generate_proposal(job_description: str) -> dict:
    logger.info("upwork: generating proposal fields")
    fields = llm.proposal_fields(job_description)
    title = fields.get("titleOfSystem") or "Untitled proposal"

    logger.info("upwork: generating application copy")
    application_body = llm.application_copy(job_description)

    logger.info("upwork: copying proposal doc from template %s", config.PROPOSAL_TEMPLATE_ID)
    proposal_id = google_client.copy_doc(config.PROPOSAL_TEMPLATE_ID, f"[Automation] {title}")
    google_client.share_doc(proposal_id, role="reader")
    google_client.fill_doc(
        proposal_id,
        {
            "titleOfSystem": fields.get("titleOfSystem", ""),
            "briefExplanationOfSystem": fields.get("briefExplanationOfSystem", ""),
            "stepByStepBulletPoints": fields.get("stepByStepBulletPoints", ""),
            "leftToRightFlowWithArrows": fields.get("leftToRightFlowWithArrows", ""),
            "aboutMeBulletPoints": fields.get("aboutMeBulletPoints", ""),
            "offer": fields.get("offer", ""),
        },
    )
    proposal_url = google_client.doc_url(proposal_id)

    logger.info("upwork: appending tracking row to sheet %s", config.TRACKING_SHEET_ID)
    row_index = google_client.append_row(
        config.TRACKING_SHEET_ID,
        config.TRACKING_SHEET_RANGE,
        [
            datetime.now(timezone.utc).strftime("%d-%m-%Y %H:%M"),
            title,
            job_description,
            fields.get("briefExplanationOfSystem", ""),
            "",
            "",
            proposal_url,
            "",
            "",
        ],
    )

    final_body = application_body.replace("$$$", proposal_url)
    return {
        "application_body": final_body,
        "proposal_url": proposal_url,
        "row_index": row_index,
    }


@app.task(name="tasks.upwork_finalize_proposal")
def upwork_finalize_proposal(
    row_index: int,
    base_connects: str = "",
    boosted_connects: str = "",
    loom_url: str = "",
) -> dict:
    if not isinstance(row_index, int) or row_index <= 0:
        raise ValueError(f"upwork_finalize_proposal: invalid row_index {row_index!r}")

    base = (base_connects or "").strip()
    boosted = (boosted_connects or "").strip()
    if base and boosted:
        connects_text = f"{base} + {boosted}"
    else:
        connects_text = base or boosted

    loom = (loom_url or "").strip()

    updates: dict[str, str] = {}
    if connects_text:
        updates[f"{config.TRACKING_SHEET_NAME}!{config.TRACKING_SHEET_CONNECTS_COLUMN}{row_index}"] = connects_text
    if loom:
        updates[f"{config.TRACKING_SHEET_NAME}!{config.TRACKING_SHEET_LOOM_COLUMN}{row_index}"] = loom

    if updates:
        logger.info("upwork: finalizing row %s with %s", row_index, list(updates.keys()))
        google_client.update_cells(config.TRACKING_SHEET_ID, updates)
    else:
        logger.info("upwork: finalize called for row %s with no values; skipping", row_index)

    return {"row_index": row_index, "updated_columns": list(updates.keys())}
