#!/usr/bin/env python3
"""Generate a self-contained, glanceable dashboard.html from posts.csv.

Presentation layer for the manual social tracker. Storage + stats live in
`social_log.py`; this script reuses its read/parse helpers, computes the
reach-first views the operator looks at *while writing*, and renders a single
self-contained HTML file (all data inlined, no server, no fetch).

  python build_dashboard.py            # writes dashboard.html next to posts.csv
  python build_dashboard.py --open     # ...and open it in the default browser

The output is gitignored — it bakes in private LinkedIn impressions and this
repo is public.

Sections, top to bottom (matches what an operator needs mid-write):
  1. This week's plan   — a Mon-Sun grid: what type to post each remaining day
                          to hit the 40/30/20/10 mix, with a proven hook example.
  2. Mix this week      — posted-so-far vs target, as bars.
  3. Top posts          — ranked by IMPRESSIONS (the metric we optimize), expandable.
  4. Best hooks         — openers ranked by impressions.
  5. Reach by bucket    — median impressions by post_type and by format.

Reach-first by design: the operator told us impressions matter most, so every
ranking here is by views, not engagement (the CLI `report` leads with engagement).
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import statistics
import webbrowser
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_PATH = HERE / "dashboard.html"

# Reuse storage + parsing from social_log.py (single source of truth).
_spec = importlib.util.spec_from_file_location("social_log", HERE / "social_log.py")
sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl)

# Weekly target counts at 7 posts/week, derived from TARGET_MIX (playbook 12.1).
# 40/30/20/10 -> 3/2/1/1 (sums to 7). Authority rounds up, social-proof keeps its slot.
WEEKLY_TARGET = {"authority": 3, "educational": 2, "personal": 1, "social-proof": 1}
TYPE_ORDER = ["authority", "educational", "personal", "social-proof"]
TYPE_LABEL = {
    "authority": "Authority",
    "educational": "Educational",
    "personal": "Personal",
    "social-proof": "Social proof",
}


def _views(row: dict) -> int | None:
    return sl._int(row.get("views", ""))


def _week_bounds(today: date) -> tuple[date, date]:
    """Monday..Sunday containing `today`."""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def _bucket_medians(rows: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[int]] = {}
    for r in rows:
        v = _views(r)
        if v is None:
            continue
        groups.setdefault((r.get(key) or "(none)").strip() or "(none)", []).append(v)
    out = [
        {"bucket": k, "n": len(v), "med": int(statistics.median(v))}
        for k, v in groups.items()
    ]
    out.sort(key=lambda d: d["med"], reverse=True)
    return out


def _best_hook_for(rows: list[dict], post_type: str) -> dict | None:
    """Highest-impression post of a given type, for use as an inspiration example."""
    cand = [r for r in rows if (r.get("post_type") or "") == post_type and _views(r)]
    if not cand:
        return None
    best = max(cand, key=lambda r: _views(r) or 0)
    return {"hook": (best.get("hook") or best.get("content") or "")[:160],
            "views": _views(best), "format": best.get("format") or "?"}


def _plan(rows: list[dict], today: date) -> dict:
    """What to post each remaining day this week to hit the mix."""
    monday, sunday = _week_bounds(today)
    this_week = [
        r for r in rows
        if r.get("platform") == "linkedin"
        and monday.isoformat() <= (r.get("posted_at") or "") <= sunday.isoformat()
    ]
    posted_by_type: dict[str, int] = {}
    posted_by_day: dict[str, list[str]] = {}
    for r in this_week:
        t = r.get("post_type") or "(none)"
        posted_by_type[t] = posted_by_type.get(t, 0) + 1
        posted_by_day.setdefault(r.get("posted_at", ""), []).append(t)

    # Deficit per type, biggest first — that's the posting priority queue.
    deficit: list[str] = []
    for t in TYPE_ORDER:
        need = max(0, WEEKLY_TARGET[t] - posted_by_type.get(t, 0))
        deficit += [t] * need

    # Lay the 7-day grid; fill needed types into upcoming empty days in priority order.
    days = []
    q = list(deficit)
    for i in range(7):
        d = monday + timedelta(days=i)
        iso = d.isoformat()
        done = posted_by_day.get(iso, [])
        rec = None
        if not done and d >= today and q:
            rec = q.pop(0)
        days.append({
            "iso": iso,
            "name": d.strftime("%a"),
            "is_today": d == today,
            "is_past": d < today,
            "posted": done,
            "recommend": rec,
        })

    return {
        "monday": monday.isoformat(),
        "sunday": sunday.isoformat(),
        "posted_by_type": posted_by_type,
        "days": days,
        "leftover": q,  # couldn't be slotted (week's nearly over) — show as "catch up"
    }


# ---------- rendering ----------

CSS = """
* { box-sizing: border-box; }
body { margin:0; background:#0d1117; color:#e6edf3; font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }
.wrap { max-width:1100px; margin:0 auto; padding:28px 20px 80px; }
h1 { font-size:22px; margin:0 0 2px; }
h2 { font-size:15px; text-transform:uppercase; letter-spacing:.08em; color:#7d8590; margin:34px 0 12px; }
.sub { color:#7d8590; font-size:13px; margin:0 0 6px; }
.card { background:#161b22; border:1px solid #30363d; border-radius:10px; padding:16px; }
.grid7 { display:grid; grid-template-columns:repeat(7,1fr); gap:8px; }
.day { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px; min-height:96px; }
.day.today { border-color:#2f81f7; box-shadow:0 0 0 1px #2f81f7; }
.day.past { opacity:.5; }
.day .dn { font-weight:600; font-size:13px; color:#7d8590; }
.day .rec { margin-top:8px; font-weight:600; font-size:13px; }
.pill { display:inline-block; padding:2px 8px; border-radius:20px; font-size:12px; font-weight:600; }
.t-authority { background:#1f6feb33; color:#79c0ff; }
.t-educational { background:#23863633; color:#7ee787; }
.t-personal { background:#9e6a0333; color:#e3b341; }
.t-social-proof, .t-social { background:#a371f733; color:#d2a8ff; }
.t-rest, .t-none { background:#30363d; color:#7d8590; }
.posted { font-size:12px; color:#7ee787; margin-top:6px; }
.bar { height:10px; background:#21262d; border-radius:6px; overflow:hidden; margin-top:4px; }
.bar > span { display:block; height:100%; }
.mixrow { margin-bottom:12px; }
.mixrow .lab { display:flex; justify-content:space-between; font-size:13px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th { text-align:left; color:#7d8590; font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; padding:6px 8px; border-bottom:1px solid #30363d; }
td { padding:8px; border-bottom:1px solid #21262d; vertical-align:top; }
tr.post { cursor:pointer; }
tr.post:hover td { background:#1c2230; }
.views { font-weight:700; color:#79c0ff; white-space:nowrap; }
.body { display:none; }
.body td { background:#0d1117; color:#adbac7; white-space:pre-wrap; font-size:13px; padding:14px 16px; }
.hookrow td:first-child { font-weight:600; }
.flag { color:#e3b341; }
.muted { color:#7d8590; }
.bars .brow { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.bars .blab { width:120px; font-size:13px; }
.bars .bfill { height:18px; border-radius:4px; background:#1f6feb; }
.bars .bn { font-size:12px; color:#7d8590; }
""".strip()

JS = """
function tog(id){var e=document.getElementById(id);e.style.display=e.style.display==='table-row'?'none':'table-row';}
""".strip()


def _pill(t: str) -> str:
    cls = "t-" + (t or "none")
    return f'<span class="pill {cls}">{html.escape(TYPE_LABEL.get(t, t or "?"))}</span>'


def _esc(s: str) -> str:
    return html.escape(s or "")


def render(rows: list[dict], today: date) -> str:
    li = [r for r in rows if r.get("platform") == "linkedin"]
    with_views = [r for r in li if _views(r) is not None]
    plan = _plan(rows, today)

    # ---- 1. weekly plan grid ----
    cells = []
    for d in plan["days"]:
        cls = "day" + (" today" if d["is_today"] else "") + (" past" if d["is_past"] else "")
        inner = f'<div class="dn">{d["name"]}{" • today" if d["is_today"] else ""}</div>'
        if d["posted"]:
            inner += "".join(f'<div class="posted">✓ {_esc(TYPE_LABEL.get(p,p))}</div>' for p in d["posted"])
        elif d["recommend"]:
            inner += f'<div class="rec">Post: {_pill(d["recommend"])}</div>'
        elif d["is_past"]:
            inner += '<div class="posted muted">— none —</div>'
        else:
            inner += '<div class="rec muted">free / flex</div>'
        cells.append(f'<div class="{cls}">{inner}</div>')
    grid = f'<div class="grid7">{"".join(cells)}</div>'

    catchup = ""
    if plan["leftover"]:
        items = " ".join(_pill(t) for t in plan["leftover"])
        catchup = f'<p class="sub flag">⚠ Behind this week — still owe: {items} (double up to catch the mix)</p>'

    # proven-hook examples for each type still needed this week
    needed_types = {d["recommend"] for d in plan["days"] if d["recommend"]} | set(plan["leftover"])
    examples = ""
    for t in TYPE_ORDER:
        if t not in needed_types:
            continue
        ex = _best_hook_for(li, t)
        if ex:
            examples += (
                f'<tr><td>{_pill(t)}</td>'
                f'<td class="muted">best {_esc(ex["format"])} · {ex["views"]} views</td>'
                f'<td>{_esc(ex["hook"])}…</td></tr>'
            )
    if examples:
        examples = (
            '<h2>Proven angles for what you still owe</h2>'
            '<div class="card"><table><thead><tr><th>Type</th><th>Track record</th>'
            '<th>Top hook to riff on</th></tr></thead><tbody>'
            f'{examples}</tbody></table></div>'
        )

    # ---- 2. mix this week ----
    posted = plan["posted_by_type"]
    mix_rows = ""
    for t in TYPE_ORDER:
        have, want = posted.get(t, 0), WEEKLY_TARGET[t]
        pct = min(100, int(have / want * 100)) if want else 0
        color = "#238636" if have >= want else "#1f6feb"
        mix_rows += (
            f'<div class="mixrow"><div class="lab"><span>{_pill(t)}</span>'
            f'<span class="muted">{have}/{want} this week</span></div>'
            f'<div class="bar"><span style="width:{pct}%;background:{color}"></span></div></div>'
        )

    # ---- 3. top posts by impressions ----
    top = sorted(with_views, key=lambda r: _views(r) or 0, reverse=True)[:15]
    post_rows = ""
    for i, r in enumerate(top):
        bid = f"b{i}"
        hook = (r.get("hook") or r.get("content") or "")[:90]
        post_rows += (
            f'<tr class="post" onclick="tog(\'{bid}\')">'
            f'<td class="views">{_views(r)}</td>'
            f'<td>{_pill(r.get("post_type") or "")}</td>'
            f'<td class="muted">{_esc(r.get("format") or "?")}</td>'
            f'<td>{_esc(hook)}…</td>'
            f'<td class="muted">{_esc(r.get("posted_at") or "")}</td></tr>'
            f'<tr class="body" id="{bid}"><td colspan="5">{_esc(r.get("content") or "")}</td></tr>'
        )

    # ---- 4. best hooks ----
    hooks = sorted(with_views, key=lambda r: _views(r) or 0, reverse=True)[:12]
    hook_rows = ""
    for r in hooks:
        hook_rows += (
            f'<tr class="hookrow"><td>{_esc((r.get("hook") or "")[:120])}</td>'
            f'<td class="views">{_views(r)}</td>'
            f'<td>{_pill(r.get("post_type") or "")}</td></tr>'
        )

    # ---- 5. reach by bucket ----
    def bars(title: str, data: list[dict]) -> str:
        if not data:
            return ""
        mx = max(d["med"] for d in data) or 1
        rows_ = ""
        for d in data:
            w = int(d["med"] / mx * 100)
            rows_ += (
                f'<div class="brow"><div class="blab">{_esc(d["bucket"])}</div>'
                f'<div class="bfill" style="width:{w}%"></div>'
                f'<div class="bn">{d["med"]} med · n={d["n"]}</div></div>'
            )
        return f'<h2>{title}</h2><div class="card bars">{rows_}</div>'

    by_type = bars("Median impressions by post type", _bucket_medians(li, "post_type"))
    by_fmt = bars("Median impressions by format", _bucket_medians(li, "format"))

    med_all = int(statistics.median([_views(r) for r in with_views])) if with_views else 0

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Social Dashboard</title><style>{CSS}</style></head><body><div class="wrap">
<h1>LinkedIn dashboard <span class="muted" style="font-weight:400">· {len(li)} posts · median {med_all} impressions</span></h1>
<p class="sub">Reach-first. Generated {today.isoformat()} · week of {plan["monday"]} → {plan["sunday"]}</p>

<h2>This week's plan</h2>
{catchup}
{grid}
{examples}

<h2>Mix this week vs target (40/30/20/10)</h2>
<div class="card">{mix_rows}</div>

<h2>Top posts by impressions <span class="muted" style="text-transform:none;letter-spacing:0">— click a row for the full post</span></h2>
<div class="card"><table><thead><tr><th>Views</th><th>Type</th><th>Format</th><th>Hook</th><th>Date</th></tr></thead>
<tbody>{post_rows}</tbody></table></div>

<h2>Best hooks by impressions</h2>
<div class="card"><table><thead><tr><th>Hook</th><th>Views</th><th>Type</th></tr></thead>
<tbody>{hook_rows}</tbody></table></div>

{by_type}
{by_fmt}

</div><script>{JS}</script></body></html>"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate dashboard.html from posts.csv")
    ap.add_argument("--open", action="store_true", help="open in the default browser")
    ap.add_argument("--date", help="override today (YYYY-MM-DD), for testing the planner")
    args = ap.parse_args(argv)

    rows = sl._read_rows()
    if not rows:
        print("no posts logged yet — nothing to render.")
        return 0

    today = date.fromisoformat(args.date) if args.date else date.today()
    OUT_PATH.write_text(render(rows, today), encoding="utf-8")
    print(f"wrote {OUT_PATH}  ({len(rows)} posts)")
    if args.open:
        webbrowser.open(OUT_PATH.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
