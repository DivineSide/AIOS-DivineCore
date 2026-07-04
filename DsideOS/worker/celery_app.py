# -*- coding: utf-8 -*-
"""Celery app for DsideOS — content-pipeline job worker.

Standalone broker/backend (own Redis). Tasks live in worker.tasks. A nightly
beat task purges expired job folders.
"""
from celery import Celery

from .settings import settings

celery_app = Celery(
    "dsideos",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_track_started=True,          # so the API sees STARTED, not just PENDING
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=settings.JOB_TTL_HOURS * 3600,
    worker_prefetch_multiplier=1,     # long jobs — don't hoard the queue
    # Bound how long any single job can occupy a worker. A full run legitimately
    # takes several minutes (extract + proofread + parallel RAG marking + build),
    # but must not run unbounded: a crafted many-page PDF whose OCR chunks never
    # reach a terminal state could otherwise pin a worker for hours (per-chunk
    # salvage no longer fails fast). Hard kill at 20 min; soft (raises inside the
    # task) at 18 min so cleanup can run.
    task_soft_time_limit=18 * 60,
    task_time_limit=20 * 60,
    # Retry broker connection on startup and on stale-connection errors
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=3,
    broker_pool_limit=None,           # disable connection pool — reconnect per publish
    beat_schedule={
        "cleanup-expired-jobs": {
            "task": "worker.tasks.cleanup_jobs",
            "schedule": 3600.0,        # hourly
        },
        # Flip jobs stuck in RUNNING past the hard time limit to FAILED. A worker
        # that is SIGKILLed (hard time limit, OOM, LibreOffice/PyMuPDF segfault)
        # can't run its own except block, so meta.json stays RUNNING forever and
        # the UI spins indefinitely. This reaper is the safety net.
        "reap-stuck-jobs": {
            "task": "worker.tasks.reap_stuck_jobs",
            "schedule": 300.0,         # every 5 min
        },
    },
)
