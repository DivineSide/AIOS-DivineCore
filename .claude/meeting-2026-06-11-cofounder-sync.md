# Co-founder Sync — 2026-06-11

**Attendees:** Mayank, Shubham, Pang
**Purpose:** follow up on KPIs, surface what's pending across the business, re-check the long-term goals, and align on the next sprint. Driver: Pang.

> How to run this: top to bottom. Sections 1-2 are status (fast). Section 3 is the real work (decisions). Section 4 is Pang's update. Fill the blanks live.

---

## 1. Goals check — does the destination still hold?

**North star (locked 05-31):** $50K MRR + 100K followers by **May 2027**.

**Phase arc (harvest, do not design):**
- **Phase 0 — NOW (weeks 1-4): Validate.** Goal: **2 paying clients in 4 weeks.** Locked ~06-06, so the clock runs to roughly **2026-07-04**.
- Phase 1 (months 2-4): go deep, 2nd/3rd workflow per client, repeat across 2-3 institutes.
- Phase 2 (months 5+): harvest the repeating patterns into AIOS.
- Phase 3 (later, optionality): AIOS as a product.

**Questions for the table:**
- [ ] Is $50K MRR + 100K by May 2027 still the number, or does it need adjusting now that the niche is locked?
- [ ] Phase 0 deadline is ~2 weeks out. Are 2 paying clients in 4 weeks still realistic, or do we reset the clock?
- [ ] **Kill criteria** was left blank at the 06-05 lock ("revisit the niche only if we don't land __ pilots in __ weeks"). We should fill it in today: _____ pilots in _____ weeks.

---

## 2. KPI scoreboard — follow-up on the 06-05 lock

Rule from 05-31: a KPI with no system behind it is a wish. Mark each hit/miss and name the blocker.

### Mayank (CEO / Engineering / Video)
| KPI | Weekly target | Hit? | Blocker |
|---|---|---|---|
| Founder-led sales calls | 4 booked + held | | |
| YT long-form | 1 | | |
| YT shorts | 2 | | |
| Infra hours | 21 | | |
| India beachhead build | moved weekly | | |

### Shubham (Research & Ops / Outreach)
| KPI | Weekly target | Hit? | Blocker |
|---|---|---|---|
| LinkedIn DMs | 50 | | |
| Partner / outreach | 3-5 | | |
| Discovery-call synthesis | 1 doc/week | | |
| Pre-call audits | 1 per booked call | | |

### Pang (Developer / Marketing / Delivery)
| KPI | Weekly target | Hit? | Blocker |
|---|---|---|---|
| LinkedIn posts | 7 | | |
| LinkedIn connection requests | 140 | | (was bottlenecked on connection limits — status?) |
| LinkedIn cold DMs | 70 | | |
| LinkedIn engagement comments | 70 | | |
| X tweets | 35 | | |
| X quality replies | 140 | | |
| Cold email (joint w/ Mayank) | 1,500/wk | | |
| Cold calls | started 06-09, target TBD | | dialer shipped this week — set the target today |

**Decision:** the 06-09 cold-call start has no weekly target. **Lock a cold-call number today** now that the dialer + CRM exist.

---

## 3. What's pending across the business (the decisions blocking us)

These are the open threads holding up Phase 0. Each needs an owner and a date, not just discussion.

### 3a. The offer is two different products right now — is that intentional?
There's real drift between our own docs:
- **India / beachhead track** (`icps/coaching`): entry offer = **AI question-paper / content generation** — validated, the owner named it unprompted as his #1 time sink.
- **US track** (`offer.md` §00): entry offer = **reviews + referrals + Google review replies + lead follow-up** — a local-growth play, still a *working hypothesis*, and one of us already pushed back that established centers have enough leads.

These are not the same product. One is a content/product workflow; the other is a marketing/growth workflow.
- [ ] **Decide:** is running two different entry offers per market deliberate (India = product pain, US = growth pain), or are we splitting focus before we've validated either?
- [ ] Owner: ________  By: ________

### 3b. Discovery calls — the gate on everything else
The US offer, the guarantee numbers, and pricing are all marked "lock after 5-10 discovery calls with real US tutoring owners."
- [ ] How many discovery calls have we actually held so far? _____
- [ ] If it's near zero, **this is the bottleneck.** Booking discovery calls is more urgent than any build.
- [ ] Target: ____ discovery calls booked by next sync.

### 3c. Numbers still marked TBD (can't pitch without them)
- [ ] **Guarantee X / Y** ("pay nothing until we book X consults in Y weeks") — still blank.
- [ ] **Retainer pricing** — still blank, both India and US.
- [ ] These unlock from discovery (3b), not from more analysis. Note them as downstream of 3b.

### 3d. Sprint accountability — it didn't run; proposal to run it next week
Honest status: the 06-05 all-hands outreach sprint (~100 touches/day each, daily scoreboard, Sunday review) **did not happen.** That's the real reason we still have no client. Not intent, no system behind it.

**Proposal (Pang):** run the sprint **next week, Pang + Shubham**, two-person and actually accountable this time.
- [ ] Daily touch target each: _____
- [ ] Daily scoreboard posted in the group, hit or miss, by _____ each day.
- [ ] Sunday review: touches → replies → meetings booked.
- [ ] Agree Mayank's role in it (or whether he runs his own India track in parallel).

### 3e. Open builds with no status
- [ ] **Website still not built.** This is the front door for every outreach motion. Who owns it, and what's the date?
- [ ] **No update from Mayank on the builds** — the India connection build and the ecom connection build. Need a real status on each: where they are, what's blocking, when they move.

### 3f. Shubham — no contact, outreach unaccounted for
- [ ] Zero contact from Shubham this week. He committed to outreach (50 LinkedIn DMs/wk, 3-5 partner outreach, synthesis doc) and there's no visibility into any of it.
- [ ] Need a straight status today: what actually got done, and what's the blocker.
- [ ] Set a check-in cadence so this isn't invisible again — daily number in the group, same as everyone.

### 3g. Stale docs flagged (housekeeping, assign and move on)
- [ ] `README.md` still describes the pre-pivot generic vision, no mention of the coaching niche.
- [ ] `shared/context/playbooks/` is still beauty-DTC and hasn't been migrated to coaching.
- [ ] Upwork / Instantly channel copy still carries old positioning.

---

## 4. Update from Pang's side (what shipped this week)

The outbound + tracking infrastructure to actually run the US dialing motion is now built:

- **Leads CRM + KPI dashboard on Supabase** (`/crm`) — deployable, persists the prospect pipeline (positive-reply cadence) and daily KPI counters.
- **Stats & History** rebuilt around **daily-completion**, not vanity counts — measures whether the non-negotiables got done, plus old-tracker import.
- **Cold Call Dialer** — imports US lead CSVs, parses + sorts phones by time zone into morning/night calling blocks, logs dispositions, schedules follow-ups. Folded into `/crm` as a tab (API under `/crm/api/dialer`).
- **Social post tracker** (`/log-post` + `/social-review`) + LinkedIn Apify importer — log each post, LLM classifies it, see which hook/format/type performs.
- **Platform decision resolved (06-10):** we build it ourselves (Twilio + Systeme.io/client-CRM + Claude), **not** GoHighLevel. Mayank's Sharon rebuttal killed the GHL speed case (the A2P / Google Business waits are identical either way). Guardrails: timebox the build + use Twilio Advanced Opt-Out for STOP/TCPA compliance.
- **Reliable Medicare — in progress today.** Actively working on it now, pushing to get everything they've asked for done by end of day today.

### My positive-reply → booked-call cadence (locked 06-10)
There's an actual system behind "they replied" → "call booked," not guesswork. Built from speed-to-lead data (5-min reply = 21x more likely to qualify) + Lee Hinkin's cold-reply-to-meeting method. Full doc: `shared/context/sales-and-delivery/positive-reply-cadence.md`.

**Three principles:**
1. **Speed wins** — reply within 5 minutes. Treat a positive reply like an alarm. Promised assets (Loom/audit) go out same day, rough beats late.
2. **Own the booking** — agree the exact time in the conversation (offer 2 slots in their timezone), then I add it to Calendly and send the invite. Never make a warm lead self-book.
3. **Follow up past comfortable** — they already raised their hand. Run the full cadence before calling anyone dead.

**The cadence (Day 0 = their positive reply):**
- **Day 0 (within 5 min):** answer their exact question + LinkedIn connect. HOT → propose 2 times / offer to call now. WARM → send the value asset + soft 2-time ask.
- **+1** email bump, fresh times. **+2** switch channel (warm call if I have the number, else LinkedIn DM). **+3** primary call push + voicemail + text. **+4** send something genuinely useful + re-ask. **+5** light angle. **+7** break-up ("should I close this out?"). **+14 / +30 / monthly** light nurture.
- Classify every reply HOT vs WARM the moment it lands; compress the cadence for HOT.

**Tracked in the CRM** (`/crm`), one row per prospect, filtered by "next touch = today" each morning, so nothing falls through.

**What I'm blocked on / need from you:**
- [ ] A locked cold-call weekly target (see §2).
- [ ] Clarity on the offer fork (§3a) so I'm dialing US leads with the right pitch.
- [ ] LinkedIn connection-request bottleneck — still capping the cold-DM pipeline.

---

## 5. Decisions we don't leave without

- [ ] Goals confirmed or adjusted (§1)
- [ ] Kill criteria filled in (§1)
- [ ] Every KPI marked hit/miss with a named blocker (§2)
- [ ] Cold-call weekly target locked (§2)
- [ ] Offer fork resolved: one product or two, deliberately (§3a)
- [ ] Discovery-call count named + next-sync target set (§3b)
- [ ] Next-week sprint agreed: Pang + Shubham, daily targets + scoreboard (§3d)
- [ ] Status pulled from Mayank on the builds + website owner/date set (§3e)
- [ ] Shubham gives a straight outreach status + check-in cadence set (§3f)
