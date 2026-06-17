# Log Post

Log a LinkedIn or X post the moment you publish it. Paste the post after the
command (`/log-post <paste the full post>`); if nothing is pasted, ask for the
post text, platform, and URL, then proceed.

You classify the post against the playbook taxonomy, then append a row to the
tracker CSV via the helper script. **Storage and stats are owned by
`tools/social-tracker/social_log.py` — never hand-edit `posts.csv`.**

## Fast path — pre-classified posts

If the pasted text already contains a `---TRACKER---` ... `---END---` block (the
writing assistant added it via `tools/social-tracker/tracker-prompt.md`), trust
those field values instead of re-classifying. Still verify `hook` and `closing`
are verbatim against the post body, strip the block out of the `content` you
save, then jump straight to step 4. This is the normal case for batch-pasting
several posts at once — log each one in turn.

## Steps

1. **Load the taxonomy.** Read `shared/context/playbooks/linkedin-playbook.md`
   §07 (frameworks) and §12.1 (content mix) if it isn't already in context.
   The X equivalent is `x-playbook.md` when the post is for X.

2. **Get the inputs.** You need: the full post text, the platform
   (`linkedin` | `x`), and ideally the post URL. Ask only for what's missing.

3. **Classify** the post. Fill every field from the post itself — do not ask
   the user to categorize, that's your job:
   - `post_type` — `authority` | `educational` | `personal` | `social-proof` (playbook §12.1)
   - `framework` — `PAS` | `SLA` | `case-study` | `BAB` (§07)
   - `funnel_stage` — `top` (authority/educational) | `middle` (personal) | `bottom` (social-proof)
   - `topic` — 1–3 word tag (e.g. "AI agents", "cold outreach")
   - `format` — `list` | `story` | `insight` | `question` | `case-study` | `hot-take` | `tutorial` | `announcement` | `other`
   - `differentiator` — which distinction the post draws (§01): `breadth-vs-depth` | `context-layer` | `embedded-expertise` | `os-framing` | `guarantee` | `none`. **If `none`, flag it** — every post is supposed to draw one (§01 / §11 checklist).
   - `hook` — the opening 1–2 sentences, verbatim
   - `closing` — the final 1–2 sentences, verbatim

4. **Write the post body to the inbox file** (avoids shell-quoting issues with
   multiline content): use the Write tool to put the raw post text into
   `tools/social-tracker/.inbox.txt`.

5. **Append the row** by running, from the repo root:
   ```
   python tools/social-tracker/social_log.py add \
     --platform <p> --url "<url>" \
     --post-type <t> --framework <f> --funnel-stage <s> \
     --topic "<topic>" --format <fmt> --differentiator <d> \
     --hook "<hook>" --closing "<closing>" \
     --content-file tools/social-tracker/.inbox.txt
   ```
   Use `--posted-at YYYY-MM-DD` only if the post wasn't published today.
   On Windows use `python` (PowerShell); the script is cross-platform.

6. **Push to the CRM Content tab.** Logging only writes the local `posts.csv`;
   the `/crm` dashboard reads the Supabase `content_posts` table, which is a
   separate sync. The user authorized this push to run on every `/log-post` (so
   posts appear on the dashboard without a manual sync). The HTTP sync
   (`sync_to_crm.py`) doesn't work from here (the VPS serves a self-signed
   cert), so the writer runs inside the api container over SSH. Run these two
   commands with the Bash tool (PowerShell lacks `<` input redirection), from
   the repo root:
   ```
   python tools/social-tracker/dump_posts_json.py > .crm-posts-tmp.json
   ssh root@srv1445995.hstgr.cloud 'docker exec -i divinecore-v2-api-1 python -c "import sys,json; from sales_os.crm import supabase_writer as w; print(w.bulk_upsert_content_posts(json.load(sys.stdin)))"' < .crm-posts-tmp.json
   ```
   It upserts every post by `post_id` (safe to re-run, never duplicates) and
   prints the row count written. Then delete `.crm-posts-tmp.json`. If the push
   fails (VPS down, or the `ssh root@srv1445995.hstgr.cloud` allow rule isn't
   set), the local log still stands — tell the user and move on; it will sync on
   the next `/log-post` or `/social-review`.

7. **Confirm** back to the user in one line: the post_id, the classification you
   chose, that it was pushed to the `/crm` Content tab, and a reminder that
   metrics get filled in the weekly `/social-review`. If `differentiator` came
   out `none`, say so plainly so they can decide whether to edit the live post.

## Notes

- One post per invocation. Metrics (views/likes/...) are intentionally left
  blank — they're collected weekly via `/social-review`.
- The CSV is gitignored (LinkedIn impressions are private analytics, repo is
  public). It lives only on this machine.
