"""Upwork application generator — single-user web form.

GET  /upwork           -> render the form
POST /upwork           -> enqueue pipeline, block on result, render the result page
POST /upwork/finalize  -> patch connects + loom into the existing tracking-sheet row
"""

import logging
from pathlib import Path

from celery import Celery
from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upwork"])

_celery = Celery("api", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

PIPELINE_TIMEOUT_SECONDS = 180
FINALIZE_TIMEOUT_SECONDS = 30


@router.get("/upwork", response_class=HTMLResponse)
def upwork_form(request: Request):
    return _templates.TemplateResponse("upwork_form.html", {"request": request})


@router.post("/upwork", response_class=HTMLResponse)
def upwork_run(request: Request, job_description: str = Form(...)):
    job_description = job_description.strip()
    if not job_description:
        return _templates.TemplateResponse(
            "upwork_result.html",
            {"request": request, "error": "Job description was empty."},
            status_code=400,
        )

    try:
        async_result = _celery.send_task("tasks.upwork_generate_proposal", args=[job_description])
        result = async_result.get(timeout=PIPELINE_TIMEOUT_SECONDS)
    except CeleryTimeoutError:
        logger.exception("upwork: pipeline timed out after %ss", PIPELINE_TIMEOUT_SECONDS)
        return _templates.TemplateResponse(
            "upwork_result.html",
            {"request": request, "error": f"Pipeline timed out after {PIPELINE_TIMEOUT_SECONDS}s."},
            status_code=504,
        )
    except Exception as exc:
        logger.exception("upwork: pipeline failed")
        return _templates.TemplateResponse(
            "upwork_result.html",
            {"request": request, "error": f"Pipeline failed: {exc}"},
            status_code=500,
        )

    return _templates.TemplateResponse(
        "upwork_result.html",
        {
            "request": request,
            "application_body": result.get("application_body", ""),
            "proposal_url": result.get("proposal_url", ""),
            "script_url": result.get("script_url", ""),
            "row_index": result.get("row_index", -1),
        },
    )


@router.post("/upwork/finalize", response_class=HTMLResponse)
def upwork_finalize(
    request: Request,
    row_index: int = Form(...),
    base_connects: str = Form(""),
    boosted_connects: str = Form(""),
    loom_url: str = Form(""),
):
    if row_index <= 0:
        return _templates.TemplateResponse(
            "upwork_finalized.html",
            {"request": request, "error": f"Invalid row index: {row_index}"},
            status_code=400,
        )

    try:
        async_result = _celery.send_task(
            "tasks.upwork_finalize_proposal",
            args=[row_index, base_connects, boosted_connects, loom_url],
        )
        result = async_result.get(timeout=FINALIZE_TIMEOUT_SECONDS)
    except CeleryTimeoutError:
        logger.exception("upwork: finalize timed out after %ss", FINALIZE_TIMEOUT_SECONDS)
        return _templates.TemplateResponse(
            "upwork_finalized.html",
            {"request": request, "error": f"Update timed out after {FINALIZE_TIMEOUT_SECONDS}s."},
            status_code=504,
        )
    except Exception as exc:
        logger.exception("upwork: finalize failed")
        return _templates.TemplateResponse(
            "upwork_finalized.html",
            {"request": request, "error": f"Update failed: {exc}"},
            status_code=500,
        )

    return _templates.TemplateResponse(
        "upwork_finalized.html",
        {
            "request": request,
            "row_index": row_index,
            "updated_columns": result.get("updated_columns", []),
        },
    )
