# Dashboard

Regenerate and open the LinkedIn/X performance dashboard — the glanceable,
reach-first view to look at *while writing today's post*.

Storage + stats live in `tools/social-tracker/`; this command just rebuilds the
HTML from the current `posts.csv` and opens it.

## Steps

1. Run, from the repo root:
   ```
   python tools/social-tracker/build_dashboard.py --open
   ```
   On Windows use `python` (PowerShell); the script is cross-platform.

2. Confirm in one line what it shows so the user knows where to look:
   - **This week's plan** — Mon-Sun grid, what post type to write each remaining
     day to hit the 40/30/20/10 mix, with a proven hook example per type.
   - **Mix this week** — posted-so-far vs target.
   - **Top posts** and **best hooks** ranked by impressions (reach-first).
   - **Median impressions by post type / format.**

## Notes

- The dashboard reads only what's in `posts.csv`. If metrics look stale, the user
  hasn't run `/social-review` yet (that's where impressions get filled in).
- `dashboard.html` is gitignored — it bakes in private impressions and the repo
  is public. It lives only on this machine.
- Reach-first by design: every ranking is by views/impressions, not engagement.
  The CLI `report` is the engagement-led counterpart.
