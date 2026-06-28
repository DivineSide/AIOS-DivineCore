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
    # Warm the Celery broker connection at startup so the first HTTP request
    # doesn't hit a cold / uninitialized connection pool.
    try:
        celery_app.connection().ensure_connection(max_retries=3)
    except Exception:
        pass
    yield


app = FastAPI(title="DsideOS — Content Pipeline", version="0.1.0", lifespan=lifespan)

SUPPORTED_UPLOAD_EXTS = {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def require_token(authorization: str = Header(default="")) -> None:
    """Defence-in-depth API auth. If DSIDEOS_API_TOKEN is configured, every
    protected route requires `Authorization: Bearer <token>` (constant-time
    compared). If the token is blank the check is a no-op — the API is then
    expected to be reachable only via the authenticated console proxy on
    localhost (the public nginx /api route was removed)."""
    expected = settings.DSIDEOS_API_TOKEN
    if not expected:
        return
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

    input_dir = jobs.input_dir(job_id)
    dest = (input_dir / f"upload{ext}").resolve()
    # defence-in-depth: ensure the write stays inside the job's input dir
    if not str(dest).startswith(str(input_dir.resolve())):
        raise HTTPException(400, "Invalid upload path.")
    dest.write_bytes(data)


# ── upload-driven endpoints ─────────────────────────────────────────────────

@app.post("/api/extract", response_model=JobAccepted, dependencies=[Depends(require_token)])
def extract(file: UploadFile = File(...)):
    """Any input file -> universal questions JSON. (Step 1 of the pipeline.)"""
    job_id = jobs.new_id()
    jobs.create(job_id, workflow="extract")
    _save_upload(job_id, file)              # file on disk BEFORE dispatch
    extract_task.apply_async(args=[job_id], task_id=job_id, retry=True)
    return JobAccepted(job_id=job_id)


@app.post("/api/full", response_model=JobAccepted, dependencies=[Depends(require_token)])
def full(
    file: UploadFile = File(...),
    paper_name: str = Form("Paper"),
    format: str = Form("format-1"),
    font: str = Form("krutidev"),
    title_hindi: str = Form(""),
    subtitle_hindi: str = Form(""),
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
    jobs.create(job_id, workflow="full", **meta)
    _save_upload(job_id, file)
    full_task.apply_async(args=[job_id, meta], task_id=job_id, retry=True)
    return JobAccepted(job_id=job_id)


# ── AI-generative endpoint (no upload — subject + count) ─────────────────────

VALID_SUBJECTS = {
    "uk-history", "uk-geography", "uk-culture",
    "uk-general-studies", "general-gk", "hindi",
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
    jobs.create(job_id, workflow="generate", subject=subject, **meta)
    generate_task.apply_async(args=[job_id, subject, count, meta], task_id=job_id, retry=True)
    return JobAccepted(job_id=job_id)


# ── JSON-driven endpoints (the 3 workflows) ──────────────────────────────────

def _dispatch_questions_task(task, req: BuildRequest, workflow: str) -> JobAccepted:
    questions = [q.model_dump(exclude_none=True) for q in req.questions]
    meta = req.meta.model_dump()
    job_id = jobs.new_id()
    jobs.create(job_id, workflow=workflow, **meta)
    task.apply_async(args=[job_id, questions, meta], task_id=job_id, retry=True)
    return JobAccepted(job_id=job_id)


@app.post("/api/build", response_model=JobAccepted, dependencies=[Depends(require_token)])
def build(req: BuildRequest):
    """W1: questions JSON -> branded paper + class deck + answer key."""
    return _dispatch_questions_task(build_task, req, "build")


@app.post("/api/answer-key", response_model=JobAccepted, dependencies=[Depends(require_token)])
def answer_key(req: BuildRequest):
    """W3: questions JSON -> standalone answer-key PDF."""
    return _dispatch_questions_task(answer_key_task, req, "answer_key")


@app.post("/api/solutions", response_model=JobAccepted, dependencies=[Depends(require_token)])
def solutions(req: BuildRequest):
    """W2: questions JSON -> teacher solution doc (question/options/answer/explanation)."""
    return _dispatch_questions_task(solutions_task, req, "solutions")


# ── polling + download ────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}", response_model=JobStatus, dependencies=[Depends(require_token)])
def job_status(job_id: str):
    meta = jobs.read_meta(job_id)
    if not meta:
        raise HTTPException(404, "Unknown job_id.")
    known = {"job_id", "status", "stage", "n_questions", "outputs", "error", "created_at"}
    return JobStatus(
        job_id=job_id,
        status=meta.get("status", "UNKNOWN"),
        stage=meta.get("stage"),
        n_questions=meta.get("n_questions"),
        outputs=meta.get("outputs", []),
        error=meta.get("error"),
        created_at=meta.get("created_at"),
        extra={k: v for k, v in meta.items() if k not in known},
    )


@app.get("/api/files/{job_id}/{name}", dependencies=[Depends(require_token)])
def download(job_id: str, name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "Invalid filename.")
    path = jobs.output_dir(job_id) / name
    if not path.is_file():
        raise HTTPException(404, "File not found.")
    return FileResponse(str(path), filename=name)
