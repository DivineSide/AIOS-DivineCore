# Delivery — DivineSide

> **⚠️ SUPERSEDED (pre-2026-06-06, beauty DTC).** Niche pivoted to education / coaching. This delivery SOP describes the old 8-week beauty pilot and is not yet migrated. Do NOT use it to set client expectations. Current niche/audience/offer: [business-info.md](../identity/business-info.md), [audience.md](../identity/audience.md), [offer.md](offer.md). Entry workflow and pricing are OPEN.

> **IN REVIEW until 2026-06-05.** The 8-week pilot delivery flow in this file (Phase 0 → Phase 4, the 8-category brain, the two parallel tracks) is the **destination** shape, not current operating reality. **Current state during the sprint (Phase 1 of the JP-model arc):** custom workflow builds at £1k–£2.5k + £350/mo retainer, audit-first, scoped per-pain per-client. The full 8-week productized pilot relaunches after the 2026-06-05 lock based on what 10 founder conversations + paid builds teach us. See [`../../../CLAUDE.md` §2](../../../CLAUDE.md) for the Phase 1/2/3 arc and [`../../../.claude/alignment-2026-05-22.md`](../../../.claude/alignment-2026-05-22.md) for the sprint structure.

> **The 8-week pilot delivery process.** What gets built, by whom, in what order, with what hand-offs. Same shape for every client; only the workflow varies.
>
> **Notion mirror:** *[paste link here after uploading to Notion]*
>
> **Loading discipline** — any agent or human delivering a pilot should load:
> 1. [`offer.md`](offer.md) — what we promised the client
> 2. [`guarantee.md`](guarantee.md) — the guarantee mechanic (TYPE A vs TYPE B, what triggers, what voids)
> 3. [`../identity/business-info.md`](../identity/business-info.md) — who we are
> 4. [`../identity/voice.md`](../identity/voice.md) — brand tone (for client-facing docs)
> 5. **This file** — the delivery process

Last updated: 2026-05-17

---

## Quick reference

| Week | Phase | Goal |
|------|-------|------|
| 0 | Pre-onboarding | Tech access in progress, kickoff scheduled, brain repo created |
| 1 | Context: kickoff + synthesis | Kickoff call run, 8-category brain drafted, signed spec (TYPE A baseline log started if applicable) |
| 2 | Context: validation | Validation call run, brain client-approved |
| 3-4 | Data | APIs live, workflow scoped |
| 5-7 | Workflow build | Built, internally tested, shipped, team trained |
| 8 | Verify + handoff | Delivery test against the kickoff spec (TYPE B) or hours-saved baseline (TYPE A); payment released on success, retainer kicks in week 9 |

---

## 01 · The two tracks

Delivery has **two things being built simultaneously**, with different rhythms. Don't conflate them.

| | The AI brain (context layer) | The workflow |
|---|---|---|
| What it is | Markdown KB about the business — strategy, voice, products, ops, decisions | The automation that saves the hours |
| Lives in | Private GitHub repo per client (one repo per brand, named `<brand>-ai-brain`) | Code + n8n / divinecore-v2 |
| Built once or maintained? | Built once, **maintained forever** | Built once, monitored ongoing |
| Owner during pilot | Pang + Mayank (kickoff + synthesis) | Whoever's building (Pang / Anish / etc.) |
| Owner in retainer | Whoever runs the weekly check-in (updates brain in-call) | Whoever monitors workflow uptime |

**Brain comes first. The workflow queries the brain.** Don't start workflow build until the brain has the categories the workflow needs.

---

## 02 · Timeline reality

The offer is **6 weeks** because that's what the client experiences. Our internal effort is closer to **3-4 weeks** of actual work.

The 2-week buffer is for **client-side** delays:
- Founder travels, takes 4 days to reply to validation
- API access takes longer than expected (some platforms require business verification)
- Scope clarifies mid-pilot, we re-scope
- Vacations, holidays, real life

Use the buffer for polish + retainer ramp-up. **Don't let it bleed into the workflow build.** If a pilot finishes in 4 weeks, ship at week 4 and use 5-6 to over-deliver (a small second workflow, a dashboard, or early retainer onboarding). Never finish at week 7+.

---

## 03 · Phase 0 — pre-onboarding

**Triggered by:** signed proposal + first 50% payment received.

**Within 24 hours of signature:**

- [ ] Create the client's brain repo: private GitHub repo `<brand-name>-ai-brain`. Pang + Mayank as collaborators.
- [ ] Create a Bitwarden collection named `<brand-name>` for all their credentials.
- [ ] Send the **tech access email** (template in §09).
- [ ] Send the **intake form** — 10-question Typeform per [`intake-form.md`](intake-form.md). Tell them: *"spend ~30 min on this before our kickoff; the hard questions we'll cover live."*
- [ ] Schedule the **kickoff call** (60-90 min, 5-7 days out — gives them time to fill the intake).
- [ ] Schedule the **validation call** (30 min, end of week 2).

By kickoff day, intake is mostly filled and tech access is in progress.

---

## 04 · Phase 1 — Context (weeks 1-2)

**Goal:** complete, client-validated AI brain in the GitHub repo.

### Week 1 — Kickoff + synthesis

**Day 1: Kickoff call (60-90 min, Pang + Mayank).**

- First 5 min: tech access status check — anything still blocked, debug live
- Walk through the intake — fill gaps, surface nuance
- The hard questions (strategy, voice, *why* decisions) only come out in conversation; the easy stuff (URLs, tools, team) is already in the intake
- Re-iterate the timeline + the 8-hours/week guarantee
- Answer any questions about the workflow scope

**Days 2-4: Synthesis (Pang).**

- Write the brain into the 8 markdown files (see §05) — one per category
- Commit to the brain repo as you go
- Anything unclear → email follow-up to the founder, don't guess

### Week 2 — Validation

**End of week 2: Validation call (30 min).**

The validation call is **quality control on the brain.** Share the 8 markdown files in advance, walk through them on the call, founder corrects/approves. This is where their voice gets honed and the decisions log gets richer.

Without this call, the brain ships with our assumptions baked in. Don't skip it.

After validation: brain is solid enough to query for workflow build. Move to Phase 2.

---

## 05 · The AI brain — 8 categories

Each becomes its own markdown file in the client's brain repo:

1. **`identity.md`** — mission, voice (banned phrases, signature phrases), positioning, founding story, what makes them different from competitors
2. **`strategy.md`** — quarterly goals, year goals, 3-year goals, top 3 priorities right now, what they're *intentionally not doing* this year
3. **`products.md`** — full catalog, hero products + why, pricing logic, bundles, planned launches this quarter
4. **`customer.md`** — primary persona, top use cases, common objections, top reasons people refund / churn
5. **`operations.md`** — org chart (who does what), vendors, tools (Shopify / Klaviyo / Gorgias / etc.), returns policy, key SOPs
6. **`channels.md`** — active marketing channels, cadence, top-performing content/ads, influencer relationships
7. **`numbers.md`** — revenue trajectory (last 12 months), AOV, top sellers, conversion rate, returning customer %, LTV/CAC if known
8. **`decisions.md`** — **the moat.** Why they price the way they do, why they chose specific tools / manufacturers, recent strategic decisions and reasoning, things they tried that didn't work

**The decisions log is the most important file.** It's what makes the brain *theirs*, not generic. Agencies don't ask, founders don't write it down, but it's the difference between a brain that "knows the brand" and one that "just has facts." Update it forever.

The intake doc sent in Phase 0 = these 8 files turned into questions.

---

## 06 · Phase 2 — Data (weeks 3-4)

**Goal:** data flowing, baseline logged, workflow scoped.

- [ ] All API access live (resolve any leftover blockers from Phase 0)
- [ ] Test data pulls from each integration — confirm we can query what we need
- [ ] **Start the baseline log (week 3)** — the team logs the function we're automating: who does it, how long, how often. This becomes the comparison for the week-4 guarantee.
- [ ] Iterate the brain — Phase 1 surfaces gaps, the data integration surfaces more (their actual data often contradicts what they said in the kickoff). Update the relevant brain files.
- [ ] Workflow scoped in detail — what it does, what it *doesn't*, what the success metric looks like

By end of week 4: baseline captured, workflow ready to build.

---

## 07 · Phase 3 — Workflow build + ship (weeks 5-6)

**Goal:** workflow live, team trained, hours measured.

The full build SOP lives in **[`workflow-build.md`](workflow-build.md)** (prereq check, n8n vs divinecore-v2 decision, where things commit). High-level checklist:

- [ ] Confirm prereqs per [`workflow-build.md`](workflow-build.md) §01 (API keys, brain validated, scope written)
- [ ] Build the workflow (1-2 weeks of internal dev — most of weeks 5-6)
- [ ] Internal testing — does it actually do what it promises? Edge cases?
- [ ] **Ship to live** at start of week 6
- [ ] **Walkthrough call** with the team that'll use it — show them how to use it, what to watch for, how to escalate
- [ ] Monitor for the rest of week 6, fix issues fast
- [ ] **Measure hours saved** — same log as the baseline. Compare. Report.

**Guarantee outcome** (per [`guarantee.md`](guarantee.md), variant agreed at kickoff):
- TYPE B target met (all functions work as specced at week 8) → invoice goes out, buyer pays
- TYPE A target met (≥ 10 hrs/week saved vs. baseline by end of month 2) → invoice goes out, buyer pays
- Target not met → no payment + $500 paid from Pang's pocket per the guarantee. Own it (per [`sales-playbook.md`](sales-playbook.md) §08), then optionally make a make-good offer (build a second workflow free, or extend the build period until target hits).

---

## 08 · Phase 4 — Handoff + retainer transition (week 8 → week 9)

**Goal:** clean transition into the ~£2.5k/month Foundation retainer.

- [ ] Handoff doc in the brain repo — what we built, how it runs, how to escalate, what to watch for
- [ ] Retainer kickoff call (30 min) — confirms the weekly cadence, sets the next workflow priority
- [ ] First weekly check-in booked for week 9

The retainer is **default-on** per [`offer.md`](offer.md). Default behavior: brain repo stays in client ownership, we keep commit access, weekly check-in starts week 9.

If they opt out: clean handoff. They keep their brain repo (it's theirs), we revoke our commit access, deliver final docs, leave the door open.

---

## 09 · Tech access protocol

### The vault — Bitwarden (free tier)

Why Bitwarden:
- Free for small teams
- Encrypted at rest
- Shared collections per client
- Simple enough that any client can use it without a security degree

If a client insists on something else: 1Password fallback (paid). **Never** Slack, email, or plaintext.

Per-client setup: one Bitwarden collection named `<brand-name>` with all their credentials, accessible to Pang + Mayank + whoever else needs it.

### The tech access email (sent in Phase 0)

Template:

```
Subject: Tech access — getting [Brand] set up

Hey [Founder],

Welcome to your DivineSide pilot. Kickoff is [date].

Before we meet, we need access to a handful of tools so we can move
fast in week 3. Here's the checklist:

1. Shopify Admin API key — [instructions link]
2. Klaviyo API key — [instructions link]
3. Gorgias API key (or whatever helpdesk) — [instructions link]
4. Meta Ads — invite [our-account-email] as Analyst
5. Google Analytics / GA4 — invite [our-account-email] as Viewer
6. [Any others specific to their stack — surface from the intake]

Send creds securely via the Bitwarden invite I just sent — please
don't email or Slack them.

If anything's blocked or unclear, flag it now and we'll handle it on
the kickoff call.

— [Pang / Mayank]
```

### Confirm in kickoff

First 5 min of kickoff: tech access status check. Anything still blocked, debug live. Don't move on to the intake walkthrough until we have a path forward on every API.

---

## 10 · Brain maintenance in the retainer

Brain updates happen **during the weekly 30-min check-in**, not async. The pattern:

- Founder mentions something new — a product launch, a strategic shift, a recent decision, a hire
- Whoever's on the call takes 2-min notes during the call
- After the call, commits the update to the relevant brain file (`decisions.md`, `products.md`, etc.)
- Quarterly: full brain review (compare current state to the 8-category baseline, flag drift, prune anything stale)

**The decisions log gets updated nearly every week.** Other files get touched as needed. After 6 months, the brain is dramatically richer than at handoff — that's the lock-in. By month 12, switching providers means losing a year of accumulated context, which no competitor can rebuild.

---

## 11 · What this doc is, what it isn't

**It is:**
- The SOP for running a pilot from signature → retainer transition
- Same flow regardless of niche (skincare or otherwise) — fixed shape, variable subject
- A living doc — first 5 pilots will reveal what to tighten

**It isn't:**
- Niche-specific delivery flows (we don't fragment by client type yet)
- A workflow build guide — that's separate (templates emerge after first 3-5 pilots)
- The retainer playbook — once we have 3+ retainers running, write `retainer.md` with detailed weekly cadence

**Update cadence:** revise after each pilot. Append a `## 12 · Lessons` one-liner per pilot.

---

## 12 · Lessons

*(Add a one-liner per pilot — what went over budget on time, where the brain broke down, what the decisions log captured that you didn't expect, whether the validation call caught real errors.)*
