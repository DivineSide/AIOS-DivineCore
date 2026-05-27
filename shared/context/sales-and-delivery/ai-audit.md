# AI Audit — DivineSide

> ⚠️ **DEFERRED, to be discussed further.** Status as of 2026-05-22, re-confirmed 2026-05-25.
>
> AI audit as a paid £2,500 product was killed: no buyer will pay £2,500 for just a diagnostic when the actual offer is "we run your systems as a managed service." Running 10+ free interviews per prospect is also not viable at scale.
>
> **The methodology in this doc is genuinely useful.** The workflow drill, the AI-fit test, the opportunity matrix, the "yesterday morning" interview technique — all real. They feed the **Phase 1 customer-discovery sprint** per [`../../../CLAUDE.md` §2](../../../CLAUDE.md) (the JP-model arc) and may yet reappear as part of a different product shape after the 2026-06-05 lock.
>
> **Do not pitch this as a paid product to clients.** Treat as a methodology reference until the productization decision at 2026-06-05.

---

> **Original framing (preserved below for reference).** The 2-week diagnostic engagement. Interview the team, map the workflows, quantify the bottlenecks, package the report with an ROI-anchored roadmap. The audit produces a pipeline of build candidates each priced as its own engagement.
>
> **Notion mirror:** *[paste link here after uploading to Notion]*
>
> **Loading discipline** — anyone running an audit should load:
> 1. [`offer.md`](offer.md) — for build-engagement context (audits feed the pipeline of builds)
> 2. [`guarantee.md`](guarantee.md) — TYPE B build guarantee referenced in Phase 7
> 3. [`../identity/voice.md`](../identity/voice.md) — for the final report tone
> 4. The persona file ([`../identity/pang.md`](../identity/pang.md)) — for whoever runs the calls
> 5. **This file** — the audit SOP

Last updated: 2026-05-18 (deferred 2026-05-22)

Built on Monk AI Group's 5-step framework + their worksheet PDF + the "yesterday morning" interview technique.

---

## 00 · Lock status

| Decision | Status |
|---|---|
| Interviews per audit | **LOCKED: 7-8** (1 sponsor + 1-2 dept heads + 4-6 ICs across 1-2 departments) |
| Workflows deep-dived in final report | **LOCKED: 2** |
| Audit price for first 3 audits | **LOCKED: £2,500** (then raises to £5,000) |
| Audit guarantee | **LOCKED: 10× savings refund.** If the audit doesn't surface at least one opportunity worth £25,000+ in annualized savings, 100% refund. |
| Recoverable-on-build credit | **LOCKED: No.** Audit fee is non-recoverable. |
| Offer-stack position | **OPEN.** Standalone product, or wedge into existing pilot. Pending cofounder meeting. |

---

## 01 · The 2-week engagement

| Phase | When | What | Output | Time |
|---|---|---|---|---|
| 0. Scoping | Pre-audit | Fit, price, departments, interview roster, dates | Signed SOW | 30-60 min |
| 1. Interviews | Week 1 (days 1-5) | 7-8 interviews + workflow drill on each surfaced workflow | 1-page note per person | 45-60 min each |
| 2. Map workflows | Week 2 (days 1-2) | High-friction workflows visualized | Workflow maps (Miro/FigJam) | 1-2 days |
| 3. Quantify | Week 2 (day 3) | Cost of each bottleneck | Cost table | 0.5 day |
| 4. Solve + prioritize | Week 2 (day 4) | AI-fit verification + opportunity matrix + solution sketch | Matrix + sketches | 1 day |
| 5. Package | Week 2 (day 5) | 5-slide report | PDF report | 1 day |
| 6. Deliver | End of week 2 | Present to exec team | Live 45-min presentation | 1 hour |
| 7. Build pitch | +48h after delivery | SOW for top Quick Win | Signed build engagement | 30 min |

Total elapsed: 10 business days. Internal hours: ~25-30.

---

## 02 · Phase 0 — Scoping call

**Attendees:** executive sponsor + Pang.
**Duration:** 30-60 min.
**Goal:** confirm fit, agree price, narrow focus to 1-2 departments, lock the 7-8 person interview roster, set start date.

### Questions to ask the sponsor

- What's the highest-level business goal this year, in your words?
- Where in the operation do you feel friction? (3 min uninterrupted)
- What have you already tried (other agencies, tools, hires)?
- How many people on the team? What does each one own?
- **Which department is costing you the most in manual work right now?** (Or: if we could only audit ONE department this engagement, which?)
- What's your authority to commit? Anyone else signs off?
- Any legal, privacy, or compliance constraints? (NDAs, regulated industry, recording rules)
- How do I contact each interviewee to schedule?

### Narrowing the interview list

The sponsor will ask *"what do you mean? Who should I pick?"* Don't leave them to guess. Give them criteria.

**Step 1 — Pick 1-2 departments.** No more. Audit goes shallow if it tries to cover everything.

- **Default recommendation: sales or marketing first.** Hours saved in these departments link directly to revenue (performance roles), so the ROI math is sharpest and the buy-in for the build engagement is easier.
- Otherwise: whichever department the sponsor named as highest-cost / most-friction.

**Step 2 — For each department, pick the people:**
- **1 department head** (knows the destination, the targets, the strategy)
- **2-3 ICs** doing the actual work (know where the manual friction lives day-to-day)

**Step 3 — Add the executive sponsor.** They count as 1 interview. They set the business objectives the audit is run against.

**Default mix (2 departments):** 1 sponsor + 2 heads + 4-5 ICs = 7-8 interviews.
**Single-department audit:** 1 sponsor + 1 head + 2-3 ICs = 4-5 interviews; use any extra slots on more ICs if the team is deeper.

### SOW deliverable

- Business objectives (3 bullets in their words)
- Departments locked for this audit
- 7-8 person interview list with booked dates (or booking channel agreed)
- Audit price (£2,500 for first 3 audits)
- Report delivery date
- Build-pitch follow-up date

---

## 03 · Phase 1 — Interviews (the core work)

**Cadence:** 7-8 interviews per audit.
**Format:** 45-60 min each, live video call (Zoom/Meet). Record + auto-transcribe (Tactiq / Otter / Fathom). Take notes during; transcript is backup.

**Why include ICs:** the CEO knows the destination, the IC knows where the friction lives. Skipping ICs is the most common failure mode in audits.

### Interview structure

**Open (1-2 min): rapport + frame**

Small talk, get them comfortable. Then transition:

> "Alright, let's jump in. I'm here to understand the boring, nitty-gritty parts of your work, the bits you hate doing, and how AI can help eliminate them. I'm not selling anything on this call. Whatever you tell me stays between us until the report goes back to your team. Sound good?"

**Q1 (always): "Walk me through yesterday morning. What did you do first, then what?"**

Let them describe naturally. The moment they hit a manual or repetitive step, STOP and run the Workflow Drill on it.

**Q2 (always): "Other than this, what do you feel is the most manual and repetitive part of your job?"**

Run the Workflow Drill on whatever they name.

**Close (3 min):**
- Anyone else I should talk to who knows more about this?
- Anything else I should be asking that I'm not?

### The Workflow Drill

For every workflow surfaced, run the drill.

**Primary directive: "Walk me through it step by step. Open this app, click here, copy this, paste that. Don't skip steps."**

Let them narrate the whole flow.

**During the walkthrough — ask when triggered:**

| Trigger | Question |
|---|---|
| You don't understand why a step is being done | "Why are you doing this?" |
| You don't recognize a tool they mention | "What's [tool name]? What does it do?" |
| Data appears (they pull or receive something) | "Where does the data come from?" |
| Data exits (they send or save something) | "Where does it go?" |

**At the end of the walkthrough — always ask:**

1. **How many times a week do you do this?** → AI-fit Q4 (frequent?) + Phase 3 ROI math
2. **How long does each cycle take?** → Phase 3 ROI math
3. **Is there anything else that touches this workflow? Anyone else, any other systems?** → Cross-team visibility + identifies more interviewees
4. **What happens if this breaks? What happens if you don't do it?** → Risk + downstream cost

### Verification before ending the interview

Can you answer the 4 AI-fit questions for every workflow you drilled?
- Input structured? (from the tools + data source they described)
- Output predictable? (from the step-by-step)
- Decisions rule-based? (from the "why" answers during the walkthrough)
- Frequent? (from "how many times a week")

If anything is unclear, ask the clarifier *now*. Goal: zero async follow-up.

### Per-interview output (1 page)

- Role + tenure (from sponsor brief, not asked in interview)
- Top 1-3 pain points (verbatim quote)
- Per pain point: full workflow drill notes (steps, the "why" answers, tools, data flow, frequency, duration, what else touches it, what if broken)
- Estimated hours/week wasted per workflow
- AI-fit notes (yes/no/unclear per test question)

---

## 04 · Phase 2 — Map workflows

**Tool:** Miro or FigJam (free).

**What to map:** all high-friction workflows surfaced across interviews (typically 3-5). The top 2 get deep-dived in the report (Phase 5). The rest live in the opportunity matrix without dedicated workflow maps.

**Format:** boxes for steps, arrows for flow. Per step, annotate:
- Time taken
- Tool used
- Manual / partial / automated marker
- Bottleneck steps in red

---

## 05 · Phase 3 — Quantify each bottleneck

**Math (from Monk's worksheet):**

For each top workflow:

| Variable | What |
|---|---|
| A | Hours wasted per employee per day |
| B | Number of employees doing this task |
| C | Loaded hourly cost = (salary + benefits + tools) / 2,080 |

- Daily cost = A × B × C
- Weekly = Daily × 5
- Annual = Weekly × 52

**Output:** cost table showing annual £ wasted per bottleneck.

---

## 06 · Phase 4 — Solve + prioritize

### AI-fit test

For each bottleneck, answer 4 questions from the interview notes (the drill produced all this data; no follow-up needed if Phase 1 was done right):

| Question | Drill question that answers it |
|---|---|
| Is the input structured? | Tools + data source notes |
| Is the output predictable? | Step-by-step (what's produced at the end) |
| Are decisions rule-based? | "Why are you doing this?" notes |
| Is it frequent? | "How many times a week?" |

**Classification:**
- All 4 yes → AI handles 80%, humans do the 20% judgment. Builds well.
- 2-3 yes → maybe, scope carefully, may need partial automation.
- 0-1 yes → keep manual.

### Opportunity matrix

| | Low effort | High effort |
|---|---|---|
| **High impact** | Quick Wins (P1) | Big Swings (P2) |
| **Low impact** | Nice-to-Haves (P3) | Deprioritize |

Quick Wins are what gets built first. Big Swings go into the roadmap for a later engagement.

### Per-opportunity solution sketch

For each Quick Win:
- Current workflow (before state, from Phase 2 maps)
- Future workflow (after state, with AI in the loop)
- Estimated annualized savings (from Phase 3 math)
- Estimated build cost (proposed in Phase 7)

---

## 07 · Phase 5 — Package the report

**5-slide structure:**

| Slide | Content |
|---|---|
| 1. Scope & Objectives | Their goals in their words. Proves we listened. |
| 2. Opportunity Matrix | 2x2 visual of every opportunity surfaced. |
| 3. Roadmap | Phased timeline: P1 quick wins now, P2 big swings later. |
| 4. Opportunity Deep Dive | **Top 2 quick wins** with current vs future workflow maps. |
| 5. Money Slide | Initiative / One-Time Implementation Cost / Annualized Savings / Payback Period. |

**Output:** PDF + Google Slides backup, branded per [`../identity/voice.md`](../identity/voice.md).

---

## 08 · Phase 6 — Deliver

Live 45-min presentation to exec team + key interviewees.

| Min | Segment |
|---|---|
| 0-5 | Re-state business objectives (slide 1) |
| 5-15 | Walk the opportunity matrix (slide 2) |
| 15-25 | Roadmap + deep dive (slides 3 + 4) |
| 25-35 | Money slide (slide 5) |
| 35-45 | Q&A + commit to build SOW within 48h |

**Don't close on the call.** Always commit to a written build SOW within 48 hours.

---

## 09 · Phase 7 — Build pitch (+48h)

- **The pitch:** *"Here's the SOW for the first Quick Win. Build cost = X. Payback = Y months. Want me to start?"*
- **Per-build pricing:** ~£2,500 flat for contained workflows. Larger builds priced individually.
- **Build guarantee:** TYPE B from [`guarantee.md`](guarantee.md) (functions delivered by week 8, or full refund + £500 from Pang's pocket).

---

## 10 · Pricing & guarantee

- **First 3 audits:** £2,500 each (anchored to existing pilot pricing). After 3, raise to £5,000.
- **Payment:** 0% upfront, 100% on delivery of the report (consistent with [`offer.md`](offer.md) payment model).
- **Audit guarantee:** if the audit doesn't surface at least one opportunity worth £25,000+ in annualized savings (10× the audit fee), the audit fee is refunded 100%. The bar is easy to clear when the diagnostic is done well; the guarantee kills price friction at the buyer's end.
- **No recoverable-on-build credit.** The audit fee stays the audit fee. The audit is its own deliverable, not a deposit against future builds.

---

## 11 · Still open: offer-stack position

Two options. To be decided with cofounders.

**Option A — Standalone product.**
- Audit sells separately to anyone (cold prospects, warm intros, existing relationships).
- After the audit, most buyers convert to builds. Some don't. Both are fine.
- Pricing stack: £2,500 audit (2 weeks) → £2,500+ per build (8 weeks each) → retainer (TBD).
- **Pro:** standalone revenue even when the build doesn't happen. Wider top of funnel.
- **Con:** the audit-to-build conversion is a separate sale.

**Option B — Wedge into the existing pilot.**
- The audit replaces the pilot's scoping phase. The pilot becomes the build, anchored to one of the audit's Quick Wins.
- Pricing stack: £2,500 audit (phase 0) → £2,500 pilot/build (phase 1) → retainer (TBD). First engagement = £5,000.
- **Pro:** forces the audit-to-build sequence. 2× the existing pilot anchor.
- **Con:** harder to wedge for skeptical buyers; they have to commit to the path, not just the diagnosis.

**Working hypothesis (not locked):** Option B for hot prospects (warm intros, existing relationships like RM365). Option A for cold (Upwork, cold email). Run both, route by channel.

---

## 12 · Lessons

*(Add a one-liner per audit run. What was the actual deliverable, what surfaced, what would you change for the next one.)*
