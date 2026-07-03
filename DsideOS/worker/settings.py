# -*- coding: utf-8 -*-
"""Runtime settings for the DsideOS content-pipeline backend.

Read from environment (or a .env file in the DsideOS folder). Mirrors the
divinecore-v2 settings pattern but standalone — its own Redis, its own keys.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DSIDEOS_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(DSIDEOS_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Broker + result backend
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM
    ANTHROPIC_API_KEY: str = ""

    # Where job inputs/outputs live on disk. One folder per job_id underneath.
    JOBS_DIR: str = str(DSIDEOS_ROOT / "storage" / "jobs")

    # Auto-delete job folders older than this many hours (cleanup beat task).
    JOB_TTL_HOURS: int = 24

    # Max upload size (MB) — guards against giant files.
    MAX_UPLOAD_MB: int = 50

    # Shared bearer token. Every protected /api route requires
    # `Authorization: Bearer <token>`. The console proxy already sends this header
    # (ds-ai/console .../api/proxy uses the same DSIDEOS_API_TOKEN env var), so the
    # two just need the SAME value. If this is blank, the API refuses to serve
    # protected routes UNLESS DSIDEOS_ALLOW_OPEN_API=1 is explicitly set (local dev
    # only) — a blank token in production used to silently disable all auth.
    DSIDEOS_API_TOKEN: str = ""

    # Dev-only escape hatch: allow running with NO API token (open API). Must be
    # explicitly enabled; production never sets it, so a missing token there is a
    # hard failure instead of a silent wide-open API.
    DSIDEOS_ALLOW_OPEN_API: bool = False


settings = Settings()
