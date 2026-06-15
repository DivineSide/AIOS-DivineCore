#!/usr/bin/env python3
"""Push posts.csv up to the deployed CRM (Supabase-backed) Content dashboard.

LinkedIn impressions are author-only and entered by hand into posts.csv via
`/social-review`. This syncs that local truth up to the /crm Content tab so the
dashboard is the same on every device. Upserts by post_id, so re-running just
refreshes metrics — never duplicates.

Posts to  POST {CRM_URL}/crm/api/content/import  (Traefik basic-auth protected),
which upserts into the `content_posts` Supabase table. The server holds the
Supabase secret; this script only needs the basic-auth creds.

  CRM_AUTH=user:pass python tools/social-tracker/sync_to_crm.py
  # or set CRM_USER + CRM_PASS; CRM_URL overrides the default host.

Stdlib only (urllib), to keep tools/ dependency-free.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_URL = "https://upwork.srv1445995.hstgr.cloud"

_spec = importlib.util.spec_from_file_location("social_log", HERE / "social_log.py")
sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl)

# Columns we send (the content_posts writable set). Matches the CSV.
FIELDS = [
    "post_id", "platform", "posted_at", "url", "post_type", "framework",
    "funnel_stage", "topic", "format", "differentiator", "hook", "closing",
    "content", "views", "likes", "comments", "reposts", "bookmarks", "notes",
]


def _auth() -> str:
    # Priority: env var, then env user/pass, then a gitignored creds file. The
    # file path keeps the secret off the command line (and out of shell history /
    # logs) — drop `user:pass` on one line in tools/social-tracker/.crm-auth.
    pair = os.environ.get("CRM_AUTH")
    if not pair:
        u, p = os.environ.get("CRM_USER"), os.environ.get("CRM_PASS")
        if u and p:
            pair = f"{u}:{p}"
    if not pair:
        cred_file = Path(os.environ.get("CRM_AUTH_FILE", HERE / ".crm-auth"))
        if cred_file.exists():
            pair = cred_file.read_text(encoding="utf-8").strip()
    if not pair:
        sys.exit("Missing creds. Put `user:pass` in tools/social-tracker/.crm-auth "
                 "(gitignored), or set CRM_AUTH / CRM_USER+CRM_PASS. "
                 "These are the /crm basic-auth credentials (see infrastructure/README.md).")
    return "Basic " + base64.b64encode(pair.encode()).decode()


def main() -> int:
    rows = sl._read_rows()
    if not rows:
        print("posts.csv is empty — nothing to sync.")
        return 0

    posts = [{k: r.get(k, "") for k in FIELDS} for r in rows]
    body = json.dumps({"posts": posts}).encode()

    base = os.environ.get("CRM_URL", DEFAULT_URL).rstrip("/")
    req = urllib.request.Request(
        f"{base}/crm/api/content/import",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": _auth()},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"sync failed: HTTP {e.code} {e.reason}\n{e.read().decode()[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"sync failed: {e.reason} (is CRM_URL right and the server up?)")

    print(f"synced {out.get('upserted', '?')} of {len(posts)} posts to {base}/crm  ->  Content tab")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
