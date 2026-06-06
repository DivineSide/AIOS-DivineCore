# Summarize Last Call

Find the most recent external call in Supabase that hasn't been written up as a conversation note yet, then generate the note using the template.

## Steps

**1. Find the most recent unprocessed meeting.**

SSH into the VPS and pull the 5 most recent meetings from Supabase, ordered by date desc:

```bash
ssh -o ConnectTimeout=10 root@srv1445995.hstgr.cloud "docker exec divinecore-v2-worker-1 python -c \"
import os, httpx
url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/meetings'
headers = {'apikey': os.environ['SUPABASE_SECRET_KEY'], 'Authorization': 'Bearer ' + os.environ['SUPABASE_SECRET_KEY']}
params = {'select': 'meeting_id,title,date,duration_min,category,external_attendees', 'order': 'date.desc', 'limit': '5'}
r = httpx.get(url, headers=headers, params=params, timeout=30)
for m in r.json():
    print(f\\\"{m['date'][:16]} | {m['category']:10} | {(m['duration_min'] or 0):3}min | id={m['meeting_id']} | ext={m.get('external_attendees') or '-'} | {(m['title'] or '')[:40]}\\\")
\""
```

Then glob `shared/context/conversations/*.md` and grep for the `fathom-meeting-id:` lines to find which meetings are already processed.

The first meeting in the Supabase list whose `meeting_id` is NOT already in the conversations folder is the unprocessed one.

If all 5 most recent are processed, tell the user: "No unprocessed calls found. The most recent is [meeting_id, date, title] which is already at [filename]." Stop.

**2. Pull the full meeting details to a temp file.**

```bash
ssh -o ConnectTimeout=10 root@srv1445995.hstgr.cloud "docker exec divinecore-v2-worker-1 python -c \"
import os, httpx
url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/meetings'
headers = {'apikey': os.environ['SUPABASE_SECRET_KEY'], 'Authorization': 'Bearer ' + os.environ['SUPABASE_SECRET_KEY']}
r = httpx.get(url, headers=headers, params={'select': '*', 'meeting_id': 'eq.<MEETING_ID>'}, timeout=30)
m = r.json()[0]
print('===META==='); print(m['title']); print(m['date']); print(m['duration_min']); print(m.get('attendees') or ''); print(m.get('external_attendees') or ''); print(m.get('transcript_url') or '')
print('===SUMMARY==='); print(m.get('summary') or '')
print('===TRANSCRIPT==='); print(m.get('transcript') or '')
\"" > .claude/_meeting_<MEETING_ID>_raw.txt 2>&1
```

Substitute `<MEETING_ID>` with the actual ID. Then Read the temp file.

**3. Read it carefully.**

Look at the summary first to identify:
- Who the external person is (name, brand, role)
- What was discussed
- Outcome / next step

Then scan the transcript for:
- Verbatim quotes worth capturing under "Surprise / non-obvious quote"
- Verbatim language under "Language signal"
- Per-pillar takeaways (the 8 pillars from [shared/context/conversations/.overview.md](../../shared/context/conversations/.overview.md))
- Niche fit signal

**4. Generate the note.**

Write to `shared/context/conversations/YYYY-MM-DD-<shortname>-<channel>.md` using the template in [shared/context/conversations/.overview.md](../../shared/context/conversations/.overview.md).

Filename rules:
- Date = the call date (not today's date)
- shortname = first-name-or-brand kebab-case, e.g. `allure-hera-founder`, `rahmatul-azmi-intrepit`
- channel = `call` for Fathom-recorded meetings

Frontmatter must include:
- `date:` the call date
- `prospect:` the person's name (use "Anonymous" + descriptor if unknown)
- `brand:` their brand/company
- `channel: call`
- `niche-fit:` YES / NO / BORDERLINE
- `fathom-meeting-id:` the Supabase meeting_id (this is the dedupe key)
- `fathom-share-url:` the share URL

For each section, use what's actually in the transcript:
- **Context:** 1-2 lines on who and why
- **Stack snapshot:** platform, tools, scale (from what was said, not assumed)
- **The 8 pillars:** what's set up vs not (mark "not discussed" honestly)
- **Surprise quote:** verbatim, with translation if non-English
- **Wand wish:** what they said when asked the "wave a wand" question (or implicit if not asked directly)
- **Budget signal:** what they pay for, what they'd pay for, or "n/a" for non-decision-makers
- **Language signal:** 3-5 verbatim phrases worth keeping for marketing copy
- **Niche fit verdict:** with 1-sentence justification grounded in the locked niche line (UK ecom DTC beauty/skincare, Shopify, 3PL, £1M-£5M ARR)
- **Outcome:** explicit next step + date
- **Lessons / signals** section if the call generated insights beyond pure validation (especially for sales-craft feedback from operators)

**5. Clean up the temp file.**

```bash
rm -f .claude/_meeting_<MEETING_ID>_raw.txt
```

**6. Report back.**

Tell the user:
- Which call was processed (date, person, brand, duration)
- The filename of the new note
- 2-3 sentence summary of the key takeaway
- Flag if there are still unprocessed calls in the recent 5 (so they can run the command again)

## Notes

- **Don't duplicate transcripts in the note.** The full transcript stays in Supabase; the note distills it.
- **Don't invent niche fit.** If the call is borderline, mark it BORDERLINE and explain why.
- **Verbatim quotes win.** Paraphrased ones lose voice.
- **If the call is internal (cofounder/strategy with no external attendees), skip it** — conversations folder is for external calls only. Tell user it was skipped and check the next most recent.
- **One call per run.** If multiple unprocessed calls exist, do the most recent one and tell the user there are more.
