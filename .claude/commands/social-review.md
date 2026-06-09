# Social Review

The weekly ritual: fill in the metrics for the posts you logged this week, then
read what's working. Run it once a week (e.g. Sunday) after you've pulled views
off LinkedIn + X.

Storage and stats are owned by `tools/social-tracker/social_log.py` — never
hand-edit `posts.csv`.

## Steps

1. **List what needs metrics.** Run:
   ```
   python tools/social-tracker/social_log.py pending
   ```
   This prints each post still missing metrics, with its `post_id`, date,
   platform, hook, and URL.

2. **Collect the numbers.** For each pending post, get from the user (or they'll
   paste a batch):
   - **X**: views are public — likes, reposts, replies, bookmarks, views all
     come off the post itself.
   - **LinkedIn**: likes/comments/reposts are visible, but **views/impressions
     are author-only** — the user reads them from their own post analytics
     ("View analytics" on each post). They cannot be scraped.

   Then write them in, one call per post:
   ```
   python tools/social-tracker/social_log.py set-metrics \
     --post-id <id> --views <n> --likes <n> --comments <n> --reposts <n> --bookmarks <n>
   ```
   Pass only the metrics you have; omit the rest.

3. **Run the report:**
   ```
   python tools/social-tracker/social_log.py report
   ```
   Add `--platform linkedin` or `--platform x` to split by channel. It prints:
   the engagement leaderboard, median engagement + views bucketed by post_type /
   format / topic, and the actual-vs-target content mix (against the 40/30/20/10
   target from linkedin-playbook §12.1).

4. **Interpret it for the user** — this is the real value, don't just dump the
   table. Give a short, decisive readout:
   - **Do more of:** the post types / formats / topics / hooks with the highest
     median engagement (and views, where present).
   - **Do less of:** what consistently underperforms.
   - **Mix correction:** if the actual mix is off the 40/30/20/10 target, say
     which type to add or cut next week.
   - **Hook patterns:** look across the top posts' verbatim `hook` values for a
     repeatable opening pattern worth reusing.
   - Call out small-sample caveats — a single post is noise, not a trend.

## Notes

- Engagement = likes + comments + reposts (matches the /social-perf dashboard).
- Views are a weak cross-platform signal (LinkedIn impressions are private,
  some X scrapes miss them), so lead with engagement and treat views as
  supporting context.
- True conversion (post → DM → call) still isn't captured here — flag a standout
  post so the user can check whether it actually drove inbound, and note it in
  the post's `notes` if so.
