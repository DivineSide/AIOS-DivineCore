# New Client Setup Guide
## From zero to a live lead pipeline

---

### What you're setting up

A fully automated monthly pipeline:
1. Scrape leads from Apollo via Apify
2. Filter and qualify against ICP rules
3. Export to Google Sheet
4. Enrich each lead (website scrape + signal assignment)
5. Generate personalised cold email copy
6. Run follow-up sequences via n8n

No manual work after setup.

---

### Prerequisites

- [ ] Google Cloud project — Sheets API enabled (`credentials.json` + `token.json`)
- [ ] Apify account with Apollo scraper access
- [ ] n8n instance (cloud or self-hosted)
- [ ] `.env` file filled in (copy `.env.example`, add all keys)

---

## Step 1 — Create the client folder

```
clients/
└── your-client-name/
    ├── icps/
    │   └── your-icp-name/
    │       ├── scrape.yaml        ← copy from framework/scrape-template.yaml
    │       └── qualify.yaml       ← copy from framework/qualify-template.yaml
    ├── templates/
    │   └── your-icp-email.yaml   ← copy from framework/email-template.yaml
    └── triggers/
        └── trigger-library.yaml  ← copy from framework/trigger-library-template.yaml
```

Fill every `<FILL_IN>` in all four files.

---

## Step 2 — Fill in client-config.yaml

Copy `framework/client-config.yaml` to `clients/your-client-name/config.yaml`.

Fill in:
- `client_name`, `region`, `language`
- `sender_name`, `sender_company`
- For each ICP: `sheet_id`, paths to scrape/qualify/email/trigger files
- The 4 `pain_questions` — rewrite in your product's language

---

## Step 3 — Write the trigger library

Copy `framework/trigger-library-template.yaml` to `clients/your-client-name/triggers/trigger-library.yaml`.

Write 4-6 seasonal/industry triggers for each ICP. These become the email opener for leads where no specific signal is detected.

**Rules:**
- Must be timely — reference something happening NOW
- Must lead naturally into the pain you're solving
- No explicit research claims ("I looked at your site", "I saw you're running ads")
- No em-dashes
- Update every 4-6 weeks as seasons change

---

## Step 4 — Create the Google Sheet

```bash
python execution/export/create-sheet-us.py --client your-client-name --icp your-icp-name
```

Copy the Sheet ID from the URL into your `client-config.yaml`.

---

## Step 5 — Run a test scrape (10 leads)

```bash
python execution/scrape/apify-scrape.py \
  --client your-client-name --icp your-icp-name --limit 10
```

Review the raw JSON. Are the companies actually your ICP? Are the job titles decision-makers?
If quality looks good, run the full scrape (50 leads).

---

## Step 6 — Filter and export

```bash
python execution/scrape/filter-leads-us.py --client your-client-name --icp your-icp-name
python execution/export/sheets-export-us.py --client your-client-name --icp your-icp-name
```

---

## Step 7 — Enrich leads (signal assignment)

```bash
python execution/enrich/enrich-leads-us.py --icp your-icp-name --all-empty
```

This scrapes each lead's website, detects signals (booking widget, ad pixels, service menu),
and writes signal type (col U) + opener phrase (col V) to the sheet.

**What the enrichment does:**
- Detects signal type: reception, reactivation, speed, upsell
- Assigns a seasonal trigger as the opener (from trigger library, rotating per lead)
- Falls back to reactivation if site is blocked
- Stores extracted services in research notes (col T)

**Do NOT use:**
- Website taglines as openers — they create non-sequiturs
- "Running since YEAR" — removed from all openers
- Platform-specific ad claims ("your Facebook ads") — can't verify

---

## Step 8 — Generate copy

```bash
python scripts/generate-copy-us.py --icp your-icp-name --rows 2-50
```

Reads U+V, fills email template, writes subject + body to cols W-Z.

**Quality gate:** 150-200 words. No em-dashes. Skips empty rows.

---

## Step 9 — Review before sending

Before loading into Instantly:
- [ ] Spot-check 5-10 emails manually
- [ ] Confirm opener line flows naturally into the pain
- [ ] No em-dashes, no explicit research claims
- [ ] Authority line is niche-specific and descriptive
- [ ] CTA is one clear ask

---

## Step 10 — Import n8n workflows

Import the 4 workflow JSONs from `n8n/workflows/`:
- `positive-reply-research-v1.json` — reply classifier + Slack routing
- `follow-up-pings-v1.json` — 5-stage auto follow-up
- `stage-auto-promote-v1.json` — lead stage progression
- `stalled-lead-reminder-v1.json` — daily digest for exhausted leads

Update all credential references and Sheet IDs. Read `n8n/conventions.md` before activating.

---

## Monthly run checklist

- [ ] Run scrape for each ICP
- [ ] Filter + export to sheet
- [ ] Run enrichment (`--all-empty`)
- [ ] Run copy generation
- [ ] Spot-check 5 emails before activating Instantly sequences
- [ ] Update trigger library if season has changed

---

## Key rules

1. Never send emails without client sign-off
2. No hardcoded credentials — everything via `.env`
3. Test on 5 leads manually before full batch
4. Read `n8n/conventions.md` before touching any workflow
5. Update trigger library every 4-6 weeks
