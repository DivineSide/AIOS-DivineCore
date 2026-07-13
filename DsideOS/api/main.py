# -*- coding: utf-8 -*-
"""DsideOS content-pipeline API.

Format-agnostic: upload a paper in any supported format (docx / pdf / png / jpg),
get back deliverables in any chosen output format + font. The product's edge is
that the input format is the user's choice, not a constraint — extraction
normalises everything to one universal Unicode questions JSON, and builders
render from that.

Async by design: every endpoint that does real work returns a job_id instantly;
the frontend polls GET /api/jobs/{id} and downloads from GET /api/files/{id}/{name}.

    POST /api/extract       upload file            -> job (questions JSON)
    POST /api/full          upload file + meta     -> job (all deliverables)
    POST /api/build         questions + meta       -> job (paper + deck + key)  [W1]
    POST /api/answer-key    questions + meta       -> job (answer-key PDF)       [W3]
    POST /api/solutions     questions + meta       -> job (teacher solution)     [W2]
    GET  /api/jobs/{id}     poll status + manifest
    GET  /api/files/{id}/{name}   download one output
"""
import json
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from worker import jobs
from worker.settings import settings
from worker.tasks import (
    answer_key_task,
    build_task,
    extract_task,
    full_task,
    generate_task,
    solutions_task,
)

from .schemas import BuildRequest, JobAccepted, JobStatus
from worker.celery_app import celery_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def _dispatch(task, *args, task_id: str):
    """Dispatch a Celery task using a fresh broker connection every time.

    Using a fresh connection avoids the kombu ConnectionPool stale-socket bug
    that surfaces when apply_async is called from uvicorn's thread pool after
    the pooled connection has gone idle and been closed by Redis.
    """
    with celery_app.connection_for_write() as conn:
        task.apply_async(args=list(args), task_id=task_id, connection=conn)


app = FastAPI(title="DsideOS — Content Pipeline", version="0.1.0", lifespan=lifespan)

# DEV ONLY: cross-origin access for the local test dashboard
# (DsideOS/docs/dev-dashboard.html, opened as a file or from another port).
# Gated behind an env flag that production compose never sets — in prod, Caddy
# serves frontend and API same-origin and this middleware is never installed.
import os as _os

if _os.environ.get("DSIDEOS_DEV_CORS") == "1":
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

SUPPORTED_UPLOAD_EXTS = {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def require_token(authorization: str = Header(default="")) -> None:
    """API auth. Every protected route requires `Authorization: Bearer <token>`
    (constant-time compared) matching DSIDEOS_API_TOKEN. The console proxy already
    sends this header using the same env var, so they just need the same value.

    FAIL CLOSED: if DSIDEOS_API_TOKEN is blank, the route is REFUSED (503) unless
    DSIDEOS_ALLOW_OPEN_API=1 is explicitly set for local dev. Previously a blank
    token made this a no-op, which — combined with the public Caddy /api route —
    left every endpoint (generate/full/extract/jobs/files) reachable with no auth
    (cost bomb + cross-tenant data access). Refusing loudly surfaces the missing
    token instead of silently serving an open API in production."""
    expected = settings.DSIDEOS_API_TOKEN
    if not expected:
        if settings.DSIDEOS_ALLOW_OPEN_API:
            return  # explicit local-dev opt-in only
        raise HTTPException(
            503, "API auth not configured: set DSIDEOS_API_TOKEN (or "
                 "DSIDEOS_ALLOW_OPEN_API=1 for local dev).")
    prefix = "Bearer "
    supplied = authorization[len(prefix):] if authorization.startswith(prefix) else ""
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Unauthorized")


@app.get("/")
def health():
    return {"ok": True, "service": "dsideos-content", "version": app.version}


# ── helpers ───────────────────────────────────────────────────────────────────

def _save_upload(job_id: str, file: UploadFile) -> None:
    # SECURITY: never use the client-supplied filename as a path component — a
    # name like "../../etc/cron.d/x.docx" or an absolute path would let an upload
    # write outside the job dir (arbitrary file write -> RCE). Take only the
    # extension from the (validated) name and write to a server-generated path.
    raw = file.filename or ""
    ext = ("." + raw.rsplit(".", 1)[-1].lower()) if "." in raw else ""
    if ext not in SUPPORTED_UPLOAD_EXTS:
        raise HTTPException(400, f"Unsupported format {ext!r}. "
                                 f"Supported: {sorted(SUPPORTED_UPLOAD_EXTS)}")

    # Read with a hard cap, in chunks, so a huge upload can't be fully buffered
    # into RAM before the size check (DoS). Stop + reject as soon as we exceed it.
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    chunks, total = [], 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, f"File exceeds {settings.MAX_UPLOAD_MB} MB limit.")
        chunks.append(chunk)
    data = b"".join(chunks)

    input_dir = jobs.input_dir(job_id).resolve()
    dest = (input_dir / f"upload{ext}").resolve()
    # defence-in-depth: ensure the write stays inside the job's input dir. Use a
    # path-parent check, NOT str.startswith — "/data/jobs/ab/input" is a string
    # prefix of the SIBLING "/data/jobs/ab/input_evil/x", so startswith would admit
    # an escape. (Not exploitable today because ext is allowlisted, but correct.)
    if input_dir != dest and input_dir not in dest.parents:
        raise HTTPException(400, "Invalid upload path.")
    dest.write_bytes(data)


# ── upload-driven endpoints ─────────────────────────────────────────────────

@app.post("/api/extract", response_model=JobAccepted, dependencies=[Depends(require_token)])
def extract(file: UploadFile = File(...), x_institute_id: str = Header(default="")):
    """Any input file -> universal questions JSON. (Step 1 of the pipeline.)"""
    job_id = jobs.new_id()
    jobs.create(job_id, workflow="extract", institute_id=x_institute_id or None)
    _save_upload(job_id, file)              # file on disk BEFORE dispatch
    _dispatch(extract_task, job_id, task_id=job_id)
    return JobAccepted(job_id=job_id)


@app.post("/api/full", response_model=JobAccepted, dependencies=[Depends(require_token)])
def full(
    file: UploadFile = File(...),
    paper_name: str = Form("Paper"),
    format: str = Form("format-1"),
    font: str = Form("krutidev"),
    title_hindi: str = Form(""),
    subtitle_hindi: str = Form(""),
    x_institute_id: str = Header(default=""),
):
    """One-shot: upload a paper -> all deliverables in the chosen format + font."""
    meta = {
        "paper_name": paper_name,
        "format": format,
        "font": font,
        "title_hindi": title_hindi,
        "subtitle_hindi": subtitle_hindi,
    }
    job_id = jobs.new_id()
    jobs.create(job_id, workflow="full", institute_id=x_institute_id or None, **meta)
    _save_upload(job_id, file)
    _dispatch(full_task, job_id, meta, task_id=job_id)
    return JobAccepted(job_id=job_id)


# ── AI-generative endpoint (no upload — subject + count) ─────────────────────

VALID_SUBJECTS = {
    "uk-history", "uk-geography", "uk-culture",
    "uk-general-studies", "general-gk", "hindi", "computer",
}


@app.post("/api/generate", response_model=JobAccepted, dependencies=[Depends(require_token)])
def generate(
    subject: str = Form(...),
    count: int = Form(...),
    paper_name: str = Form("Paper"),
    format: str = Form("format-1"),
    font: str = Form("krutidev"),
    title_hindi: str = Form(""),
    subtitle_hindi: str = Form(""),
    x_institute_id: str = Header(default=""),
):
    """AI Generative: pick a subject + question count -> generate questions from
    the embedded book corpus -> same deliverables as /api/full (no file upload)."""
    if subject not in VALID_SUBJECTS:
        raise HTTPException(400, f"Unknown subject {subject!r}. "
                                 f"Valid: {sorted(VALID_SUBJECTS)}")
    if not (1 <= count <= 100):
        raise HTTPException(400, "count must be between 1 and 100.")

    meta = {
        "paper_name": paper_name,
        "format": format,
        "font": font,
        "title_hindi": title_hindi,
        "subtitle_hindi": subtitle_hindi,
    }
    job_id = jobs.new_id()
    jobs.create(job_id, workflow="generate", subject=subject,
                institute_id=x_institute_id or None, **meta)
    _dispatch(generate_task, job_id, subject, count, meta, task_id=job_id)
    return JobAccepted(job_id=job_id)


# ── JSON-driven endpoints (the 3 workflows) ──────────────────────────────────

def _dispatch_questions_task(task, req: BuildRequest, workflow: str,
                             institute_id: str = "") -> JobAccepted:
    questions = [q.model_dump(exclude_none=True) for q in req.questions]
    meta = req.meta.model_dump()
    job_id = jobs.new_id()
    jobs.create(job_id, workflow=workflow, institute_id=institute_id or None, **meta)
    _dispatch(task, job_id, questions, meta, task_id=job_id)
    return JobAccepted(job_id=job_id)


@app.post("/api/build", response_model=JobAccepted, dependencies=[Depends(require_token)])
def build(req: BuildRequest, x_institute_id: str = Header(default="")):
    """W1: questions JSON -> branded paper + class deck + answer key."""
    return _dispatch_questions_task(build_task, req, "build", x_institute_id)


@app.post("/api/answer-key", response_model=JobAccepted, dependencies=[Depends(require_token)])
def answer_key(req: BuildRequest, x_institute_id: str = Header(default="")):
    """W3: questions JSON -> standalone answer-key PDF."""
    return _dispatch_questions_task(answer_key_task, req, "answer_key", x_institute_id)


@app.post("/api/solutions", response_model=JobAccepted, dependencies=[Depends(require_token)])
def solutions(req: BuildRequest, x_institute_id: str = Header(default="")):
    """W2: questions JSON -> teacher solution doc (question/options/answer/explanation)."""
    return _dispatch_questions_task(solutions_task, req, "solutions", x_institute_id)


# ── polling + download ────────────────────────────────────────────────────────

# Map a raw internal exception string to a generic, stage-aware client message.
# The raw error (which can contain absolute server paths, LibreOffice/soffice
# stderr, or provider error bodies) stays in meta.json for server-side logs; the
# client only gets a safe summary keyed by the stage it failed in.
_STAGE_MESSAGE = {
    "extract": "Could not read the paper. Try a clearer scan or a different file.",
    "review": "Extraction failed while structuring the questions.",
    "build": "Failed to build the output documents.",
    "answer_key": "Failed to build the answer key.",
    "solutions": "Failed to build the solutions.",
    "generate_explanations": "Failed to generate explanations.",
}


def _client_error(meta: dict) -> str | None:
    if meta.get("status") != "FAILED":
        return None
    return _STAGE_MESSAGE.get(meta.get("stage"), "The job failed. Please try again.")


def _check_owner(meta: dict, x_institute_id: str) -> None:
    """Per-tenant scoping: a job may only be read by the institute that created it.

    The console proxy sends X-Institute-Id derived from the caller's verified
    session (not user input); only the console holds the API token, so a browser
    can't forge it. If a job carries an institute_id, a mismatched caller gets 404
    (not 403 — don't confirm the job exists to a non-owner). Jobs created before
    this change have no institute_id and stay readable (back-compat); once every
    create stamps it, absence only happens for legacy jobs.
    """
    owner = meta.get("institute_id")
    if owner and x_institute_id and owner != x_institute_id:
        raise HTTPException(404, "Unknown job_id.")


@app.get("/api/jobs/{job_id}", response_model=JobStatus, dependencies=[Depends(require_token)])
def job_status(job_id: str, x_institute_id: str = Header(default="")):
    meta = jobs.read_meta(job_id)
    if not meta:
        raise HTTPException(404, "Unknown job_id.")
    _check_owner(meta, x_institute_id)
    known = {"job_id", "status", "stage", "n_questions", "outputs", "error", "created_at"}
    # never surface the raw internal error string (paths / stderr / provider bodies)
    # to the client — return only the safe stage-keyed summary.
    return JobStatus(
        job_id=job_id,
        status=meta.get("status", "UNKNOWN"),
        stage=meta.get("stage"),
        n_questions=meta.get("n_questions"),
        outputs=meta.get("outputs", []),
        error=_client_error(meta),
        created_at=meta.get("created_at"),
        extra={k: v for k, v in meta.items() if k not in known and k != "error"},
    )


@app.get("/api/files/{job_id}/{name}", dependencies=[Depends(require_token)])
def download(job_id: str, name: str, x_institute_id: str = Header(default="")):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "Invalid filename.")
    # per-tenant scoping: only the owning institute may download a job's files
    meta = jobs.read_meta(job_id)
    if meta:
        _check_owner(meta, x_institute_id)
    path = jobs.output_dir(job_id) / name
    if not path.is_file():
        raise HTTPException(404, "File not found.")
    return FileResponse(str(path), filename=name)
