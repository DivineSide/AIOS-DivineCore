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
    base = {
        "job_id": job_id,
        "status": "QUEUED",
        "created_at": int(time.time()),
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
    return json.loads(p.read_text(encoding="utf-8"))


def write_meta(job_id: str, meta: dict) -> None:
    _meta_path(job_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_meta(job_id: str, **changes) -> dict:
    meta = read_meta(job_id) or {"job_id": job_id}
    meta.update(changes)
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


def cleanup_expired(ttl_hours: int) -> int:
    """Delete job folders older than ttl_hours. Returns count removed."""
    if not JOBS_DIR.exists():
        return 0
    cutoff = time.time() - ttl_hours * 3600
    removed = 0
    for d in JOBS_DIR.iterdir():
        if not d.is_dir():
            continue
        meta = read_meta(d.name)
        created = (meta or {}).get("created_at", d.stat().st_mtime)
        if created < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed
