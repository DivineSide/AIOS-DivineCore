# -*- coding: utf-8 -*-
"""Job storage on local disk — the single source of truth for a job's files.

Layout (one folder per job under JOBS_DIR):

    storage/jobs/<job_id>/
        input/      uploaded source file(s)
        output/     generated deliverables
        meta.json   {workflow, status, format, font, created_at, ...}

Celery's Redis result backend holds transient task state; THIS holds the files
and the durable metadata the API serves. Job ids are the Celery task ids, so the
API can poll Celery for live status and read this for the file manifest.
"""
import json
import shutil
import time
import uuid
from pathlib import Path

from .settings import settings

JOBS_DIR = Path(settings.JOBS_DIR)
TERMINAL_STATUSES = {"DONE", "FAILED", "TIMEOUT", "CANCELLED", "EXPIRED"}
STAGE_PROGRESS = {
    "extract": 10,
    "generate": 20,
    "review": 55,
    "generate_explanations": 70,
    "answer_key": 75,
    "solutions": 75,
    "build": 85,
}


def _now() -> int:
    return int(time.time())


def retention_seconds() -> int:
    return settings.RETENTION_DAYS * 24 * 3600


def expires_at_for(created_at: int | float | str | None) -> int | None:
    try:
        created = int(created_at) if created_at is not None else None
    except (TypeError, ValueError):
        created = None
    if created is None:
        return None
    return created + retention_seconds()


def _normalise_progress(meta: dict) -> int | None:
    value = meta.get("progress")
    if value is None:
        return None
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return None


def _apply_lifecycle_defaults(meta: dict, changes: dict | None = None) -> dict:
    """Keep lifecycle fields consistent in one place."""
    merged = dict(meta)
    if changes:
        merged.update(changes)

    created = merged.get("created_at")
    if created is None:
        created = _now()
        merged["created_at"] = created
    if merged.get("expires_at") is None:
        merged["expires_at"] = expires_at_for(created)

    status = str(merged.get("status", "QUEUED")).upper()
    merged["status"] = status

    current_progress = _normalise_progress(meta)
    explicit_progress = _normalise_progress(changes or {})
    stage_progress = STAGE_PROGRESS.get(str(merged.get("stage", "")).lower())

    if status == "DONE":
        next_progress = 100
    elif explicit_progress is not None:
        next_progress = explicit_progress
    elif current_progress is not None and stage_progress is not None:
        next_progress = max(current_progress, stage_progress)
    elif stage_progress is not None:
        next_progress = stage_progress
    elif current_progress is not None:
        next_progress = current_progress
    elif status == "QUEUED":
        next_progress = 0
    else:
        next_progress = None
    if next_progress is not None:
        merged["progress"] = max(current_progress or 0, min(100, next_progress))

    if status in TERMINAL_STATUSES and merged.get("finished_at") is None:
        merged["finished_at"] = _now()
    return merged


def new_id() -> str:
    """Mint a fresh job id. We own ids (not Celery) so the job folder + upload
    exist before any task is dispatched."""
    return uuid.uuid4().hex[:16]


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def input_dir(job_id: str) -> Path:
    return job_dir(job_id) / "input"


def output_dir(job_id: str) -> Path:
    return job_dir(job_id) / "output"


def _meta_path(job_id: str) -> Path:
    return job_dir(job_id) / "meta.json"


def create(job_id: str, **meta) -> Path:
    """Create the job folders and write initial metadata. Returns the job dir."""
    d = job_dir(job_id)
    input_dir(job_id).mkdir(parents=True, exist_ok=True)
    output_dir(job_id).mkdir(parents=True, exist_ok=True)
    created_at = _now()
    base = {
        "job_id": job_id,
        "status": "QUEUED",
        "created_at": created_at,
        "expires_at": expires_at_for(created_at),
        "progress": 0,
        "outputs": [],
        "error": None,
    }
    base.update(meta)
    write_meta(job_id, base)
    return d


def read_meta(job_id: str) -> dict | None:
    p = _meta_path(job_id)
    if not p.exists():
        return None
    # The worker rewrites meta.json many times during a run while the API polls it.
    # With atomic writes (write_meta) a torn read shouldn't happen, but tolerate a
    # transient decode error (retry once) instead of 500ing the poll.
    for attempt in range(2):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            if attempt == 0:
                import time
                time.sleep(0.05)
                continue
            return None


def write_meta(job_id: str, meta: dict) -> None:
    # Write atomically: a partial write must never be observed by a concurrent
    # read_meta (the API polls meta.json continuously while the worker updates it).
    # Write to a temp file in the same dir, then os.replace() onto meta.json — an
    # atomic rename on the same filesystem.
    import os
    import tempfile
    p = _meta_path(job_id)
    data = json.dumps(meta, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".meta.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(p))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update_meta(job_id: str, **changes) -> dict:
    meta = read_meta(job_id) or {"job_id": job_id}
    meta = _apply_lifecycle_defaults(meta, changes)
    write_meta(job_id, meta)
    return meta


def list_outputs(job_id: str) -> list[dict]:
    """Manifest of files in the job's output folder, for the API to serve."""
    od = output_dir(job_id)
    if not od.exists():
        return []
    out = []
    for p in sorted(od.iterdir()):
        if p.is_file():
            out.append({"name": p.name, "size": p.stat().st_size})
    return out


def _delete_output_files(job_id: str) -> None:
    od = output_dir(job_id)
    if od.exists():
        shutil.rmtree(od, ignore_errors=True)
    od.mkdir(parents=True, exist_ok=True)


def mark_expired(job_id: str, reason: str = "Generated files expired.") -> dict:
    _delete_output_files(job_id)
    return update_meta(job_id, status="EXPIRED", outputs=[], error=reason)


def is_expired(meta: dict, now: int | None = None) -> bool:
    if str(meta.get("status", "")).upper() == "EXPIRED":
        return True
    expires = meta.get("expires_at") or expires_at_for(meta.get("created_at"))
    if expires is None:
        return False
    return (now or _now()) > int(expires)


def list_jobs(limit: int = 50, status: str = "all", institute_id: str = "") -> list[dict]:
    """Return known jobs newest-first from filesystem metadata."""
    if not JOBS_DIR.exists():
        return []
    wanted = status.lower()
    rows: list[dict] = []
    for d in JOBS_DIR.iterdir():
        if not d.is_dir():
            continue
        meta = read_meta(d.name)
        if not meta:
            continue
        owner = meta.get("institute_id")
        if owner and owner != institute_id:
            continue
        meta = _apply_lifecycle_defaults(meta)
        if is_expired(meta):
            meta = mark_expired(d.name)
        job_status = str(meta.get("status", "UNKNOWN")).upper()
        active = job_status in {"QUEUED", "RUNNING", "PENDING"}
        if wanted == "active" and not active:
            continue
        if wanted in {"done", "history", "finished"} and active:
            continue
        rows.append(meta)
    rows.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
    return rows[: max(1, min(limit, 200))]


def cleanup_expired(retention_days: int | None = None) -> int:
    """Expire output files past retention while keeping job metadata."""
    if not JOBS_DIR.exists():
        return 0
    days = retention_days or settings.RETENTION_DAYS
    cutoff = _now() - days * 24 * 3600
    removed = 0
    for d in JOBS_DIR.iterdir():
        if not d.is_dir():
            continue
        meta = read_meta(d.name)
        if not meta:
            # Orphan folders have no history to preserve.
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
            continue
        created = int(meta.get("created_at", d.stat().st_mtime))
        if created < cutoff and str(meta.get("status", "")).upper() != "EXPIRED":
            mark_expired(d.name)
            removed += 1
    return removed


def reap_stuck(max_running_seconds: int) -> int:
    """Flip jobs stuck in RUNNING past max_running_seconds to FAILED.

    A worker that is hard-killed (Celery hard time limit, OOM, a LibreOffice /
    PyMuPDF segfault) can't run its own except block, so meta.json stays RUNNING
    forever and the UI spins indefinitely. We use meta.json's last-modified time
    as the 'last activity' signal — a live job rewrites meta on every stage
    transition, so a RUNNING job whose meta hasn't been touched in longer than the
    hard time limit is genuinely dead. Returns the number reaped."""
    if not JOBS_DIR.exists():
        return 0
    cutoff = time.time() - max_running_seconds
    reaped = 0
    for d in JOBS_DIR.iterdir():
        if not d.is_dir():
            continue
        meta = read_meta(d.name)
        if not meta or meta.get("status") != "RUNNING":
            continue
        mp = _meta_path(d.name)
        try:
            last_activity = mp.stat().st_mtime
        except OSError:
            continue
        if last_activity < cutoff:
            update_meta(d.name, status="FAILED",
                        error="Worker did not finish (timed out or crashed).")
            reaped += 1
    return reaped
