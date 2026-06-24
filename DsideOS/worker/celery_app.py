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
    beat_schedule={
        "cleanup-expired-jobs": {
            "task": "worker.tasks.cleanup_jobs",
            "schedule": 3600.0,        # hourly
        },
    },
)
