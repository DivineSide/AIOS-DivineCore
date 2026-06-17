#!/usr/bin/env python3
"""Dump posts.csv to the content_posts JSON payload on stdout.

Used by /log-post (and /social-review) to push the local tracker up to the
deployed /crm Content tab. The HTTP path (sync_to_crm.py) is dead because the
VPS serves a self-signed cert, so the working sync pipes this JSON into the
in-container Supabase writer over SSH:

    python tools/social-tracker/dump_posts_json.py > .crm-posts-tmp.json
    ssh root@srv1445995.hstgr.cloud 'docker exec -i divinecore-v2-api-1 \
      python -c "import sys,json; from sales_os.crm import supabase_writer as w; \
      print(w.bulk_upsert_content_posts(json.load(sys.stdin)))"' < .crm-posts-tmp.json

bulk_upsert_content_posts upserts by post_id, so re-running just refreshes —
never duplicates. Stdlib only; reuses social_log's reader so the field set and
CSV parsing stay in one place.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location("social_log", HERE / "social_log.py")
sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl)

# The content_posts writable set — must match sync_to_crm.FIELDS and the CSV.
FIELDS = [
    "post_id", "platform", "posted_at", "url", "post_type", "framework",
    "funnel_stage", "topic", "format", "differentiator", "hook", "closing",
    "content", "views", "likes", "comments", "reposts", "bookmarks", "notes",
]


def main() -> int:
    rows = sl._read_rows()
    posts = [{k: r.get(k, "") for k in FIELDS} for r in rows]
    json.dump(posts, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
