# Sales Playbook — DivineSide

> **⚠️ SUPERSEDED (pre-2026-06-06, beauty DTC).** Niche pivoted to education / coaching. This playbook (including the "never lead with AIOS externally" rule, which still holds) is beauty-era and not yet migrated. Do NOT generate sales copy from it. Current niche/audience/offer: [business-info.md](../identity/business-info.md), [audience.md](../identity/audience.md), [offer.md](offer.md).

> **IN REVIEW until 2026-06-05.** The end-to-end sales SOP in this file (pre-call audit, 45-min discovery call, 24h audit doc with £2.5k pilot + £2.5k/mo retainer, TYPE A/B guarantee, pilot → retainer transition) is the **destination** sales process. **Current state during the sprint (Phase 1 of the JP-model arc):** sales calls are discovery-first (5-question script from the alignment doc), transition to a custom-build pitch only if fit exists, anchor at **£1k–£2.5k per workflow + £350/mo retainer**. Do NOT use the 24h audit doc template in §06 or the offer reference in §05 as-is. They describe destination productized pricing, not what we charge today. See [`offer.md` §00](offer.md) for current operating state, [`../../../CLAUDE.md` §2](../../../CLAUDE.md) for the Phase 1/2/3 arc, and [`../../../.claude/alignment-2026-05-22.md`](../../../.claude/alignment-2026-05-22.md) for the sprint structure.

> **The end-to-end SOP for converting a cold-email reply into a paid pilot, then a retainer.**
>
> Current focus: UK skincare and beauty e-commerce brands. Stage 1 of the business model (custom AI OS builds).
>
> **Notion mirror:** https://www.notion.so/Sales-Discovery-Call-DivineSide-356d0f7e5ebd80fdbdb9ed5baec7f891?source=copy_link
>
> **Loading discipline** — any agent or human running outreach, sales calls, audits, or proposals on behalf of DivineSide should load:
> 1. [`offer.md`](offer.md) — **what we sell** (locked headline, pricing, guarantee, scope envelope)
> 2. [`business-info.md`](../identity/business-info.md) — what we do as a company, what we don't
> 3. [`voice.md`](../identity/voice.md) — brand tone
> 4. [`audience.md`](../identity/audience.md) — who we sell to
> 5. The relevant persona — [`mayank.md`](../identity/mayank.md) or [`pang.md`](../identity/pang.md) — for whoever is voicing the call/email
> 6. **This file** — process, audit doc template, follow-up cadence
> 7. [`sales-discovery-call.md`](sales-discovery-call.md) — for anything happening on a live call
> 8. [`delivery.md`](delivery.md) — for what happens after the deal closes (so the call doesn't promise things delivery can't do)
>
> This file is the human SOP that the future Sales OS module (CLAUDE.md §6 Module 2) will eventually automate.

Last updated: 2026-05-04

---

## 01 · Who we sell to

**Target profile (current focus — UK skincare/beauty, Stage 1):**

- UK-based e-commerce beauty or skincare brand
- Annual revenue between £500k and £5M
- 5-50 full-time team members
- At least one operational function visibly under-resourced (CS slow, returns manual, influencer ops eating hours, content cadence inconsistent)

**If a reply doesn't fit:**
- Clearly too small → route to commoditised offer (chatbots, simple automations)
- Clearly too big → polite decline, add to a future-pipeline list, revisit when we have case studies at scale

The qualifier line in the cold email and booking form does most of this filtering pre-call. We don't want to be on a call with a brand we can't help.

### Filtering posture by channel

The strict ICP above applies to **cold outbound only**. Other channels run on a different filter:

| Channel | Filter | Rationale |
|---|---|---|
| Cold email | Strict — UK skincare/beauty only | The niche IS the wedge — drop it and the email is generic |
| LinkedIn / Upwork / inbound | Open — qualify on budget + fit | Lead source already filtered for intent |
| Warm intro / network | Open — say yes if budget exists | Trust pre-qualifies |

**The rule: niche is for who we hunt, not for who we accept.** A non-UK lead with budget walking in through LinkedIn or Upwork = still a yes.

---

## 02 · Lead qualification

### Cold email reply / booking form qualifier

When someone replies positive to outreach, before booking a call, ask four questions inline (or as a 30-second booking form):

> **Quick context before we meet:**
> - Roughly what's your annual revenue range?
> - How many people on your team?
> - What's the one operational function eating the most time right now?
> - If there's someone else on your team who'd own this day-to-day — head of ops, CS lead, whoever runs the function we'd be helping with — feel free to bring them. Not required, just makes the call sharper.

What this surfaces:
- Fit (revenue + team size against the target profile)
- The likely diagnosis target (function under pressure)
- The multi-stakeholder situation, pre-empted

If the answers disqualify them, send a polite "we focus on £X-£Y range right now, let's circle back when you're closer to that" and don't book the call.

### Confirmation email (sent within 1 hour of booking)

- Confirms time + calendar invite
- One line of context: *"I'll spend ~20 min before our call looking at your public ops so we can skip the basics."*
- One line on notes: *"I run an AI summarizer on these calls — happy to send you the recap notes after we're done so neither of us has to scribble. Let me know if you'd rather not."*
- If they didn't fill in the four questions in the booking form, ask them in the confirmation reply

---

## 03 · Pre-call audit (20 minutes per call)

The point: walk in with **2-3 specific, concrete observations**, not a strategy. Most agencies don't do this. It's the cheapest trust-builder available.

### Public surface (10 min)

- [ ] **Tech stack** — Wappalyzer or BuiltWith. Shopify? Klaviyo? Gorgias / Zendesk / Re:amaze? Recharge? Yotpo? Tells you what's already wired and what's manual.
- [ ] **CS speed** — send a question via their contact form *and* DM their IG. Note timestamps. Check again in 24h.
- [ ] **Returns policy page** — clarity, friction, conditions. *"Email returns@..."* signals manual handling.
- [ ] **Reviews** — scan Trustpilot / Google (and Amazon if applicable). Pull the 3 most common complaints. Translate them:
  - "Wrong shade" → PDP / sizing issue
  - "Where's my order" → CS / shipping pain
  - "Leaked in transit" → packaging / returns pain
  - "No response from support" → CS bandwidth, the obvious one
- [ ] **Email welcome flow** — sign up with a throwaway. Note: how many emails, how personalized, gaps, conversion intent.
- [ ] **Hiring page / LinkedIn jobs** — what are they hiring for? Each role is a signal:
  - "CS Manager" → drowning in tickets
  - "Influencer Coordinator" → manual ops
  - "Ops Lead" → founder is bottlenecked

### Social/content surface (5 min)

- [ ] **IG / TikTok cadence** — daily? weekly? gaps? Comments replied to? Founder visible or just brand?
- [ ] **UGC / influencer activity** — collabs visible in feed? Reposted? If they're getting tagged but not amplifying, that's manual ops they're not doing.
- [ ] **DM response time** — message a product question. Time it.

### Founder/team signals (5 min)

- [ ] **LinkedIn — founder + team** — staff count, roles, tenure. High turnover = ops chaos.
- [ ] **Founder content** — posting? Frustrations? Wins? Often tells you exactly what's on their mind.
- [ ] **Press / podcast appearances** — recent interviews surface stated priorities for the year.

### Output: 3 bullets to walk in with

1. **Biggest visible gap** — concrete, specific. *"CS responds in ~36h on average; benchmark is 6h."*
2. **Probable cause** — *"Looks like Gorgias is set up but most replies still appear manual."*
3. **A guess at the highest-leverage workflow** — held loosely, ready to be wrong.

**Don't lead the call with the audit.** Let them describe their world first, then weave observations in:
> *"You mentioned CS bandwidth — I noticed when I emailed yesterday it took 30 hours to get a reply, is that typical?"*

That lands harder than *"I did an audit, here's what I found."*

---

## 04 · The discovery call (45 min)

The full call playbook lives in **[`sales-discovery-call.md`](sales-discovery-call.md)** — call structure, scripts, decision-authority branches, objection responses, risk-reversal language. Open that doc before any call.

**Notion mirror of the discovery call doc:** *[paste link here after uploading to Notion]*

### Quick reference (45 min)

| Min | Section |
|-----|---------|
| 0-5 | Rapport + meeting-notes offer |
| 5-8 | Set the schedule + decision authority |
| 8-30 | Diagnosis (why-triad → goals → pipeline → numbers → function deep-dive) |
| 30-37 | Frame the offer (with temperature checks) |
| 37-42 | Risk reversal + objections |
| 42-45 | No close — commit to proposal, lock follow-up, "anything else?" |

### Core principles (load before any call)

- Consult, don't pitch — if you're talking more than 40% of the time, recalibrate
- Don't close on the call — always commit to a written proposal within 24h
- Temperature checks throughout
- Let them feel in control (ask permission at every transition)
- Nail the why-triad and 90% of the work is done

For full scripts, branches, objection handling, and offer framing — see [`sales-discovery-call.md`](sales-discovery-call.md).

---

## 05 · The offer

The full locked offer (headline promise, naming discipline, pilot phases, pricing, guarantee, scope envelope, expansion path) lives in **[`offer.md`](offer.md)**.

**Notion mirror of the offer doc:** *[paste link here after uploading to Notion]*

### Quick reference

| | |
|---|---|
| **Headline promise** | *"Your business, running on AI."* In 8 weeks, you don't pay anything upfront and only pay on delivery. If we miss the target, you don't pay anything and I pay you $500. |
| **Pilot pricing** | Per-project, anchored at ~£2.5k (provisional, currently testing). No tiered pricing or founding-partner discount. |
| **Pilot duration** | 8 weeks (context → data → build → verify) |
| **Pilot scope** | One workflow, ≤2 weeks of build, API-accessible, measurable |
| **Retainer (Foundation)** | ~£2.5k/month (provisional). Includes context maintenance + monitoring + weekly check-in + up to 2 active workflows |
| **Retainer expansion** | +£500/month per additional active workflow |
| **Guarantee variant** | TYPE B (functions delivered, default) or TYPE A (hours saved, only when 4 explicit signals are present). See [`guarantee.md`](guarantee.md) §02. |
| **Payment** | 0% upfront, 100% on delivery, conditional on guarantee |
| **Naming externally** | "Your business, running on AI." Lead with the outcome. Upwork channel exception: lead with AIOS framing (see [`offer.md`](offer.md) §01). |

For the full strategic offer (pricing, channels, scope envelope, expansion path) see [`offer.md`](offer.md). For the guarantee mechanic (verbatim paragraphs, what triggers, voids, claim) see [`guarantee.md`](guarantee.md).

---

## 06 · The 24h audit doc

Send within 24 hours of the discovery call. **One page.** Format:

```
[Brand Name] — Pilot Audit
Your business, running on AI.

Recommended starting function: [function]
Why: [2-3 sentence diagnosis tying audit observations to what they said
on the call — not generic, specific to them]

Top 3 opportunities (ranked by hours saved per week):
1. [Highest leverage workflow] — est. [X] hrs/week saved
2. [Second] — est. [X] hrs/week saved
3. [Third] — est. [X] hrs/week saved

We recommend starting with #1.

Pilot (~£2.5k, 8 weeks)

- Weeks 1-2: Context. We learn your business (products, voice, SOPs,
  decisions). This becomes your AI brain.
- Weeks 3-4: Data. We connect the brain to [specific tools they use].
- Weeks 5-7: Build. We ship the [specific workflow] live.
- Week 8: Verify. Delivery test against the kickoff spec or the
  hours-saved baseline.

Guarantee (TYPE A or TYPE B depending on what fits this build best):
- TYPE B (default): the system performs the functions we agree on
  at kickoff by week 8. If a function is missing or doesn't work, you
  don't pay anything and I pay you $500.
- TYPE A (hours-saved, only when 4 explicit signals present): the
  system saves at least 10 hrs/week by month 2, measured against the
  baseline we agree on at kickoff. If we miss, you don't pay and I
  pay you $500.

After week 8:
Foundation retainer at ~£2.5k/month, default-on. Context maintained
as the business changes + monitoring + weekly check-in + up to 2
active workflows. Each additional workflow adds £500/month.
Month-to-month, 30-day notice.

Payment: 0% upfront, 100% on delivery (conditional on the guarantee).

Next step:
Reply to confirm and we kick off [specific week].
```

If Branch B applied (decision-maker not on call), write it to be **forwarded** — assume the reader has zero prior context.

---

## 07 · Follow-up cadence

| Day | Action |
|-----|--------|
| Day 1 (call day) | 24h audit doc sent |
| Day 3 | Follow-up call (booked on the discovery call itself) |
| Day 5 (if silent) | Light nudge: *"Quick check-in — happy to clarify anything in the doc."* |
| Day 10 (if still silent) | Specific nudge with new value: *"Was thinking about [specific thing they mentioned] — here's a thought: [observation/insight]. Worth a quick conversation?"* |
| Day 21 | Final nudge: *"Going to assume timing isn't right — happy to revisit in 3 months. Anything else useful in the meantime?"* |
| Day 90 | Re-engage with one line of new value (relevant case study, insight, or industry shift) |

Past 90 days fully cold → drop into long-cycle nurture (manual quarterly check-ins until Sales OS automates this).

---

## 08 · Pilot → retainer transition

The retainer is sold *as part of the pilot offer* (default-on, opt-out). Don't treat the transition as a separate sale.

The full delivery process (Phase 0 → Phase 4 handoff) lives in **[`delivery.md`](delivery.md)**. This section covers only the *sales-side* of the handoff — the conversation, not the operational checklist.

### Week 7-8 transition call

- Review what was shipped
- Confirm the guarantee target was hit (or address it honestly if not)
- Discuss the 2-3 highest-priority next workflows for the coming quarter
- Confirm Foundation retainer kicks in at week 9 *unless they explicitly opt out*

### If they opt out

Respect it. Leave the door open. Deliver clean handoff docs (their context layer is theirs, in their format, ready for them to maintain or hand to another agency).

### If the guarantee target wasn't hit

**Own it before they bring it up.** That's non-negotiable.

> *"We didn't hit [metric]. Here's what we learned, here's what we'd do differently, here's how we make it right."*

Per [`guarantee.md`](guarantee.md): they don't pay anything for the pilot and I pay them $500 out of pocket. That's the contracted outcome. Beyond that, optionally offer (let them pick):
1. Build one additional workflow free as a make-good (only do this if the relationship is worth saving and the failure was on our side)
2. Extend the build period free until we hit the metric (only if they're willing and the gap is small)

**The first 3-5 pilots where this happens, eat the cost.** The case study and the relationship are worth more than the lost fee. The lesson goes into the next iteration of this doc.

---

## 09 · What this doc is, what it isn't

**It is:**
- The human SOP for selling DivineSide services in 2026
- The training document the future Sales OS module will load from
- A living doc — evolves with every pilot

**It is not:**
- A script to read off verbatim — load the relevant persona file ([`mayank.md`](../identity/mayank.md) or [`pang.md`](../identity/pang.md)) so the language sounds like the human running the call
- Final on pricing — first 3-5 pilots will tell us if £5k / £2k is too low or too high
- Independent of brand voice — load [`voice.md`](../identity/voice.md) before any outreach or written proposal

**Update cadence:** after every pilot, append a one-line note to a `## 10 · Lessons` section at the bottom — what worked, what didn't, what we'd say differently next time. After 5 pilots, do a full revision pass.

---

## 10 · Lessons

*(Add a one-liner per pilot here. What worked, what didn't, what we'd say differently next time.)*
