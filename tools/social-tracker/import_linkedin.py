#!/usr/bin/env python3
"""One-time bulk import of an Apify LinkedIn-profile-posts JSON export.

Reads the export, skips reposts (only Pang's own posts), maps each post to the
tracker schema, fills engagement metrics (likes = total reactions, comments,
reposts), auto-extracts hook (first line) + closing (last line), and applies
the per-post classification in CLASSIFICATIONS below.

Views stay blank: LinkedIn impressions are author-only and never appear in a
scrape. Fill them later from your own post analytics via `social_log set-metrics`.

Usage:
    python tools/social-tracker/import_linkedin.py            # reads .import-linkedin.json
    python tools/social-tracker/import_linkedin.py --file path/to/export.json

Idempotent: re-running upserts by post_id, so it won't duplicate rows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import social_log

HERE = Path(__file__).resolve().parent
DEFAULT_EXPORT = HERE / ".import-linkedin.json"

# Pang's own profile — anything else in the export is a repost and is skipped.
OWN_USERNAME = "pang-yick-ho-a5aa6638b"

# Per-post classification, keyed by activity_urn.
# (post_type, framework, funnel_stage, format, differentiator, topic)
CLASSIFICATIONS: dict[str, tuple[str, str, str, str, str, str]] = {
    "7469887855998304256": ("educational", "SLA", "top", "story", "context-layer", "AI hooks"),
    "7469525949550645248": ("educational", "SLA", "top", "story", "context-layer", "context files"),
    "7467711137703444480": ("educational", "PAS", "top", "insight", "context-layer", "reactivation"),
    "7467352980158156800": ("educational", "PAS", "top", "list", "none", "lead response"),
    "7466986644441833472": ("personal", "SLA", "middle", "story", "none", "gym discipline"),
    "7466630208075456512": ("educational", "PAS", "top", "tutorial", "none", "Claude Code tokens"),
    "7466267528961388544": ("authority", "PAS", "top", "insight", "context-layer", "workflows vs roles"),
    "7465941981022556160": ("personal", "SLA", "middle", "story", "none", "offer clarity"),
    "7465539672107184129": ("authority", "PAS", "middle", "list", "os-framing", "AI OS benefits"),
    "7465188920398360576": ("authority", "PAS", "top", "list", "breadth-vs-depth", "revenue leaks"),
    "7463006191292416000": ("social-proof", "case-study", "bottom", "case-study", "none", "Meta ads audit"),
    "7462650010757799936": ("educational", "PAS", "top", "list", "none", "AI audit"),
    "7462278558887862272": ("personal", "SLA", "middle", "tutorial", "context-layer", "morning routine"),
    "7461933590616936448": ("educational", "PAS", "top", "list", "none", "API key security"),
    "7461555104672808960": ("educational", "SLA", "top", "story", "guarantee", "cold email offer"),
    "7461186524949377024": ("educational", "PAS", "top", "tutorial", "none", "token optimization"),
    "7460826714776981504": ("authority", "PAS", "top", "insight", "os-framing", "AI OS architecture"),
    "7460464961606025218": ("authority", "PAS", "top", "list", "os-framing", "autonomous rollout"),
    "7460103187933376512": ("educational", "PAS", "top", "list", "context-layer", "context files"),
    "7459745961419100161": ("social-proof", "case-study", "bottom", "case-study", "embedded-expertise", "marketing OS"),
    "7459387902951682048": ("authority", "BAB", "top", "announcement", "os-framing", "AI OS pivot"),
    "7450678744513703937": ("educational", "PAS", "top", "list", "none", "outreach channels"),
    "7450320424275460096": ("personal", "SLA", "middle", "story", "none", "focus"),
    "7449954853935808512": ("personal", "SLA", "middle", "story", "none", "validation"),
    "7449591585622622208": ("educational", "PAS", "top", "insight", "context-layer", "brand voice"),
    "7449227720426749952": ("educational", "SLA", "top", "story", "none", "response time"),
    "7448868533423276033": ("personal", "SLA", "middle", "list", "none", "progress update"),
    "7448511999107440640": ("educational", "PAS", "top", "list", "none", "discovery calls"),
    "7448144565284339712": ("educational", "SLA", "top", "story", "none", "cold email reply"),
    "7447785668908544001": ("educational", "PAS", "top", "list", "none", "Reddit marketing"),
    "7447424188065370112": ("educational", "PAS", "top", "tutorial", "none", "cold email setup"),
    "7447062936881356800": ("social-proof", "case-study", "bottom", "case-study", "none", "ecom workflows"),
    "7446699698964512769": ("educational", "PAS", "top", "insight", "none", "captions bottleneck"),
    "7446376605859454977": ("personal", "SLA", "middle", "list", "none", "week 3 update"),
    "7445970324837527552": ("educational", "PAS", "top", "tutorial", "none", "caption workflow"),
    "7445609556925202432": ("educational", "SLA", "top", "story", "none", "API key security"),
    "7445244659821559809": ("personal", "SLA", "middle", "story", "none", "first youtube"),
    "7444882416634130432": ("personal", "SLA", "middle", "story", "none", "leverage"),
    "7444523279417245696": ("educational", "PAS", "top", "list", "none", "levels of AI"),
    "7444163360448950272": ("educational", "PAS", "top", "list", "none", "AI audit departments"),
    "7443792796173463552": ("educational", "PAS", "top", "list", "none", "readiness checklist"),
    "7443436931633520640": ("personal", "SLA", "middle", "story", "none", "uncertainty"),
    "7443067149973196800": ("personal", "SLA", "middle", "story", "none", "first youtube"),
    "7442713344240750592": ("educational", "PAS", "top", "insight", "none", "wasted hours"),
    "7442341901107777536": ("educational", "PAS", "top", "insight", "none", "AI content review"),
    "7441980415025815552": ("educational", "PAS", "top", "insight", "none", "content consistency"),
    "7441621553848418304": ("personal", "SLA", "middle", "story", "none", "first discovery call"),
    "7441248646588764161": ("educational", "PAS", "top", "list", "none", "AI model selection"),
    "7440903596642123776": ("educational", "PAS", "top", "list", "none", "AI learning resources"),
    "7440541134201757696": ("educational", "PAS", "top", "insight", "context-layer", "brand voice"),
    "7440175905295196160": ("authority", "PAS", "top", "insight", "none", "agency dependency"),
    "7439814122998870017": ("personal", "SLA", "middle", "story", "none", "shiny object"),
    "7439453449349550080": ("personal", "SLA", "middle", "list", "none", "week 1 update"),
    "7439097532523360256": ("educational", "SLA", "top", "story", "none", "offer ICP"),
    "7438744435728969728": ("authority", "PAS", "top", "insight", "none", "data centralization"),
    "7438370855568654336": ("educational", "SLA", "top", "story", "none", "account ownership"),
    "7438022234935492608": ("educational", "PAS", "top", "insight", "none", "captions pain"),
    "7437848891422826496": ("educational", "SLA", "top", "story", "none", "AI slop review"),
    "7437487128432844800": ("personal", "SLA", "middle", "story", "none", "origin leverage"),
}


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import an Apify LinkedIn export into the tracker.")
    parser.add_argument("--file", default=str(DEFAULT_EXPORT))
    args = parser.parse_args(argv)

    export_path = Path(args.file)
    if not export_path.exists():
        print(f"export not found: {export_path}\n"
              f"Save your Apify download there (or pass --file <path>).")
        return 1

    items = json.loads(export_path.read_text(encoding="utf-8"))
    rows = {r["post_id"]: r for r in social_log._read_rows()}

    imported = skipped = unclassified = 0
    for item in items:
        author = (item.get("author") or {}).get("username", "")
        urn = (item.get("urn") or {}).get("activity_urn") or ""
        if item.get("post_type") == "repost" or author != OWN_USERNAME or not urn:
            skipped += 1
            continue

        text = item.get("text") or ""
        lines = _lines(text)
        stats = item.get("stats") or {}
        cls = CLASSIFICATIONS.get(urn)
        if cls is None:
            unclassified += 1
            print(f"  ! no classification for {urn} — imported with blank tags")
            ptype = framework = funnel = fmt = diff = topic = ""
        else:
            ptype, framework, funnel, fmt, diff, topic = cls

        post_id = f"li-{urn}"
        rows[post_id] = {
            "post_id": post_id,
            "platform": "linkedin",
            "posted_at": (item.get("posted_at") or {}).get("date", "")[:10],
            "url": item.get("url") or "",
            "post_type": ptype,
            "framework": framework,
            "funnel_stage": funnel,
            "topic": topic,
            "format": fmt,
            "differentiator": diff,
            "hook": lines[0] if lines else "",
            "closing": lines[-1] if lines else "",
            "content": text,
            "views": "",
            "likes": str(stats.get("total_reactions", 0)),
            "comments": str(stats.get("comments", 0)),
            "reposts": str(stats.get("reposts", 0)),
            "bookmarks": "",
            "notes": "apify-import",
        }
        imported += 1

    social_log._write_rows(list(rows.values()))
    print(f"\nimported {imported}, skipped {skipped} (reposts/non-Pang), "
          f"{unclassified} without classification.")
    print(f"total rows now: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
