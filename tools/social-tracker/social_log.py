#!/usr/bin/env python3
"""Manual LinkedIn + X post tracker — storage + stats.

The companion to the `/log-post` and `/social-review` slash commands. The LLM
does the part only a model can do (read a post, classify it against the
playbook taxonomy); this script does the part code should own (write a
well-quoted row, update metrics, compute the leaderboard + bucket stats +
actual-vs-target content mix).

Storage is a single CSV at `posts.csv` next to this file. Columns mirror the
existing `social_posts` Supabase schema (so it can be bulk-loaded into the
/social-perf dashboard later) plus the playbook-native strategy columns
(post_type / framework / funnel_stage / differentiator).

Data file is gitignored — LinkedIn impressions are your private analytics and
this repo is public.

Usage
-----
  add          append a freshly-classified post (metrics left blank)
  set-metrics  fill in views / likes / comments / ... for one post (weekly)
  pending      list posts still missing metrics
  report       leaderboard + bucket stats + actual-vs-target mix

Run `python social_log.py <command> -h` for per-command flags.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from datetime import date
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent / "posts.csv"

# Column order. First block mirrors the social_posts Supabase schema; the
# second block is the metrics filled in during the weekly review.
COLUMNS = [
    "post_id",
    "platform",
    "posted_at",
    "url",
    "post_type",
    "framework",
    "funnel_stage",
    "topic",
    "format",
    "differentiator",
    "hook",
    "closing",
    "content",
    "views",
    "likes",
    "comments",
    "reposts",
    "bookmarks",
    "notes",
]

METRIC_COLUMNS = ["views", "likes", "comments", "reposts", "bookmarks"]

# Target content mix — linkedin-playbook.md §12.1 (7 posts/week).
# X has no locked target yet; report shows its distribution without a target.
TARGET_MIX = {
    "authority": 0.40,
    "educational": 0.30,
    "personal": 0.20,
    "social-proof": 0.10,
}

# Soft-validated vocab (a bad value warns but still logs — never block a log).
VALID = {
    "platform": {"linkedin", "x"},
    "post_type": {"authority", "educational", "personal", "social-proof"},
    "framework": {"PAS", "SLA", "case-study", "BAB"},
    "funnel_stage": {"top", "middle", "bottom"},
    "format": {
        "list", "story", "insight", "question", "case-study",
        "hot-take", "tutorial", "announcement", "other",
    },
    "differentiator": {
        "breadth-vs-depth", "context-layer", "embedded-expertise",
        "os-framing", "guarantee", "none",
    },
}


# ---------- io ----------

def _read_rows() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_rows(rows: list[dict]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in COLUMNS})


def _next_post_id(rows: list[dict], platform: str, posted_at: str) -> str:
    """Stable-ish manual id: <platform>-<YYYYMMDD>-<n>."""
    stamp = posted_at.replace("-", "")
    prefix = f"{platform}-{stamp}-"
    n = sum(1 for r in rows if r.get("post_id", "").startswith(prefix)) + 1
    return f"{prefix}{n}"


def _warn_vocab(field: str, value: str) -> None:
    if value and field in VALID and value not in VALID[field]:
        opts = ", ".join(sorted(VALID[field]))
        print(f"  ! {field}={value!r} not in known set ({opts}) — logged anyway",
              file=sys.stderr)


def _int(value: str) -> int | None:
    value = (value or "").strip().replace(",", "")
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _engagement(row: dict) -> int | None:
    parts = [_int(row.get(c, "")) for c in ("likes", "comments", "reposts")]
    if all(p is None for p in parts):
        return None
    return sum(p or 0 for p in parts)


# ---------- commands ----------

def cmd_add(args: argparse.Namespace) -> int:
    rows = _read_rows()
    posted_at = args.posted_at or date.today().isoformat()

    content = args.content or ""
    if args.content_file:
        content = Path(args.content_file).read_text(encoding="utf-8").strip()

    for field in ("platform", "post_type", "framework", "funnel_stage",
                  "format", "differentiator"):
        _warn_vocab(field, getattr(args, field) or "")

    row = {
        "post_id": _next_post_id(rows, args.platform, posted_at),
        "platform": args.platform,
        "posted_at": posted_at,
        "url": args.url or "",
        "post_type": args.post_type or "",
        "framework": args.framework or "",
        "funnel_stage": args.funnel_stage or "",
        "topic": args.topic or "",
        "format": args.format or "",
        "differentiator": args.differentiator or "",
        "hook": args.hook or "",
        "closing": args.closing or "",
        "content": content,
        "notes": args.notes or "",
    }
    rows.append(row)
    _write_rows(rows)
    print(f"logged {row['post_id']}  [{row['platform']} / {row['post_type']} / "
          f"{row['format']}]  metrics pending")
    return 0


def cmd_set_metrics(args: argparse.Namespace) -> int:
    rows = _read_rows()
    target = next((r for r in rows if r.get("post_id") == args.post_id), None)
    if target is None:
        print(f"no post with id {args.post_id!r} — run `pending` to see ids",
              file=sys.stderr)
        return 1
    for metric in METRIC_COLUMNS:
        value = getattr(args, metric)
        if value is not None:
            target[metric] = str(value)
    _write_rows(rows)
    metrics = "  ".join(f"{m}={target.get(m) or '-'}" for m in METRIC_COLUMNS)
    print(f"updated {args.post_id}:  {metrics}")
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    rows = _read_rows()
    # A post is pending if it's missing impressions/views OR engagement (likes).
    # Bulk imports fill likes (reactions) but never views (LinkedIn impressions
    # aren't scrapeable), so the old "missing BOTH" check hid the whole backlog.
    pend = [r for r in rows
            if not (r.get("views") or "").strip()
            or not (r.get("likes") or "").strip()]
    if not pend:
        print("nothing pending - every logged post has metrics.")
        return 0
    print(f"{len(pend)} post(s) awaiting metrics:\n")
    for r in pend:
        hook = (r.get("hook") or r.get("content") or "")[:60].replace("\n", " ")
        print(f"  {r['post_id']:<22} {r['posted_at']:<11} "
              f"{r['platform']:<9} {r.get('post_type',''):<13} {hook}")
        if r.get("url"):
            print(f"  {'':<22} {r['url']}")
    return 0


def _bucket(rows: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault((r.get(key) or "(none)").strip() or "(none)", []).append(r)
    out = []
    for bucket, items in groups.items():
        eng = [e for e in (_engagement(r) for r in items) if e is not None]
        views = [v for v in (_int(r.get("views", "")) for r in items) if v is not None]
        out.append({
            "bucket": bucket,
            "count": len(items),
            "med_eng": int(statistics.median(eng)) if eng else 0,
            "med_views": int(statistics.median(views)) if views else 0,
        })
    out.sort(key=lambda r: (r["med_eng"], r["count"]), reverse=True)
    return out


def _print_bucket(title: str, rows: list[dict]) -> None:
    print(f"\n{title}")
    print(f"  {'bucket':<16} {'n':>3} {'med eng':>8} {'med views':>10}")
    for r in rows:
        print(f"  {r['bucket']:<16} {r['count']:>3} {r['med_eng']:>8} {r['med_views']:>10}")


def cmd_report(args: argparse.Namespace) -> int:
    rows = _read_rows()
    if args.platform:
        rows = [r for r in rows if r.get("platform") == args.platform]
    if not rows:
        print("no posts logged yet.")
        return 0

    scope = args.platform or "all platforms"
    print(f"=== social tracker report - {scope} ({len(rows)} posts) ===")

    # Leaderboard by engagement.
    scored = [(r, _engagement(r)) for r in rows]
    scored = [(r, e) for r, e in scored if e is not None]
    scored.sort(key=lambda t: t[1], reverse=True)
    if scored:
        print("\nTop posts by engagement (likes+comments+reposts):")
        for r, eng in scored[:args.top]:
            views = r.get("views") or "-"
            hook = (r.get("hook") or "")[:50].replace("\n", " ")
            print(f"  {eng:>5} eng  {views:>7} views  "
                  f"[{r.get('post_type','?')}/{r.get('format','?')}]  {hook}")

    _print_bucket("By post type:", _bucket(rows, "post_type"))
    _print_bucket("By format:", _bucket(rows, "format"))
    _print_bucket("By topic:", _bucket(rows, "topic"))

    # Actual vs target content mix (post_type distribution).
    print("\nContent mix vs target (linkedin-playbook 12.1):")
    total = len(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.get("post_type") or "(none)"] = counts.get(r.get("post_type") or "(none)", 0) + 1
    for ptype in ["authority", "educational", "personal", "social-proof"]:
        actual = counts.get(ptype, 0) / total
        target = TARGET_MIX[ptype]
        flag = "" if abs(actual - target) <= 0.10 else "  <-- off target"
        print(f"  {ptype:<13} actual {actual*100:4.0f}%   target {target*100:3.0f}%{flag}")
    other = {k: v for k, v in counts.items() if k not in TARGET_MIX}
    for k, v in other.items():
        print(f"  {k:<13} actual {v/total*100:4.0f}%   target   - ")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual LinkedIn + X post tracker.")
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="append a classified post")
    a.add_argument("--platform", required=True)
    a.add_argument("--url")
    a.add_argument("--posted-at", dest="posted_at", help="YYYY-MM-DD (default: today)")
    a.add_argument("--post-type", dest="post_type")
    a.add_argument("--framework")
    a.add_argument("--funnel-stage", dest="funnel_stage")
    a.add_argument("--topic")
    a.add_argument("--format")
    a.add_argument("--differentiator")
    a.add_argument("--hook")
    a.add_argument("--closing")
    a.add_argument("--content", help="post body inline")
    a.add_argument("--content-file", dest="content_file",
                   help="read post body from a file (robust for multiline posts)")
    a.add_argument("--notes")
    a.set_defaults(func=cmd_add)

    s = sub.add_parser("set-metrics", help="fill metrics for one post")
    s.add_argument("--post-id", dest="post_id", required=True)
    for metric in METRIC_COLUMNS:
        s.add_argument(f"--{metric}", type=int)
    s.set_defaults(func=cmd_set_metrics)

    p = sub.add_parser("pending", help="list posts missing metrics")
    p.set_defaults(func=cmd_pending)

    r = sub.add_parser("report", help="leaderboard + bucket stats + mix")
    r.add_argument("--platform", choices=["linkedin", "x"])
    r.add_argument("--top", type=int, default=10)
    r.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
