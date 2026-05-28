import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "divinecore",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks",
        "ops_os.integrations.fathom.processor",
        "ops_os.integrations.fathom.poller",
        "sales_os.integrations.upwork.processor",
        "sales_os.integrations.upwork_jobs.processor",
        "sales_os.integrations.instantly.processor",
        "branding_os.agents.imagyn",
        "branding_os.agents.lyra",
        "branding_os.integrations.social_perf.processor",
    ],
)

app.conf.beat_schedule = {
    "heartbeat-every-30s": {
        "task": "tasks.heartbeat",
        "schedule": 30.0,
    },
    "poll-fathom-every-10m": {
        "task": "tasks.poll_fathom_recordings",
        "schedule": 600.0,
    },
    "poll-instantly-campaigns-daily": {
        "task": "tasks.poll_instantly_campaigns",
        "schedule": crontab(hour=0, minute=30),
    },
    "ping-instantly-followups-daily": {
        # 00:00 UTC = 08:00 MYT. Scans positive replies (intent NOT in OOO/OptOut)
        # that need a follow-up reminder ping (day +1, +2, +3 after replied_at,
        # capped at DIVINESIDE_FOLLOWUP_MAX_PINGS). No-op if no replies due.
        "task": "tasks.ping_pending_followups",
        "schedule": crontab(hour=0, minute=0),
    },
    "poll-upwork-jobs-daily": {
        # 21:40 UTC = 05:40 MYT every day. Scrapes UPWORK_SEARCH_URL via
        # Apify and upserts new jobs into the upwork_jobs Supabase table.
        # No-ops if APIFY_API_TOKEN or UPWORK_SEARCH_URL is unset.
        "task": "tasks.poll_upwork_jobs",
        "schedule": crontab(hour=21, minute=40),
    },
    "poll-social-posts-daily": {
        # 22:10 UTC every day — separated from the Upwork poll so the worker
        # isn't slammed with two Apify-heavy jobs back-to-back. Scrapes every
        # configured LinkedIn profile + X handle, refreshes metrics, fans
        # out annotation tasks for unannotated posts. No-ops if APIFY_API_TOKEN
        # is unset or no profiles/handles are configured.
        "task": "tasks.poll_social_posts",
        "schedule": crontab(hour=22, minute=10),
    },
}
