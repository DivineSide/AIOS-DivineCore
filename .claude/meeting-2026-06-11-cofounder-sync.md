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

---

## 2. KPI scoreboard — follow-up on the 06-05 lock

Rule from 05-31: a KPI with no system behind it is a wish. Mark each hit/miss and name the blocker.

### Mayank (CEO / Engineering / Video)
| KPI | Weekly target | Hit? | Blocker |
|---|---|---|---|
| YT long-form | 1 | | |
| YT shorts | 2 | | |

### Shubham (Research & Ops / Outreach)
> **No KPIs right now.** Shubham has nothing concrete he's accountable for this week, and that's the problem. **We need to set his KPIs today** — fill this table in live once we agree what he actually owns (see §3e).

| KPI | Weekly target | Hit? | Blocker |
|---|---|---|---|
| | | | |

### Pang (Developer / Marketing / Delivery) — daily KPIs
These are the daily non-negotiables tracked in the CRM (`/crm`), not weekly targets. Cold emails + cold calls are weekday-only (no weekend goal).

| KPI | Daily target | Hit? | Blocker |
|---|---|---|---|
| LinkedIn posts | 1 | | |
| X tweets | 15 | | |
| LinkedIn engagement comments | 30 | | |
| X quality replies | 60 | | |
| LinkedIn connection requests | 20 | | connection-request limit still capping the cold-DM pipeline — status? |
| Cold emails (joint w/ Mayank) | 214 (weekdays) | | |
| Cold calls | 50 (weekdays) | | currently running ahead — 60 today, aiming 80 tomorrow |
| Discovery calls booked | 4 / week | | downstream of outreach landing |

---

## 3. What's pending across the business (the decisions blocking us)

These are the open threads holding up Phase 0. Each needs an owner and a date, not just discussion.

### 3a. The US offer — what Pang is actually selling
For the US, the entry offer is the **reviews + referrals + Google review replies** workflow, plus asking each prospect whether they'd want a **content machine** on top — something that generates their lecture slides, quizzes, and study material for them.

So it's not a marketing-vs-product fork to resolve: it's one growth offer (reviews / referrals / review replies) with a content-generation add-on we float in the conversation to see if it lands.
- [ ] Confirm everyone's aligned that this is the US pitch, so I'm dialing leads with the right message.

### 3b. Discovery / offer numbers — flag, don't decide yet
We don't have the data to agree on the US offer numbers (guarantee, pricing, which workflow leads) **because we have zero clients so far.** Flagging it so it's on the radar, but there's nothing to decide today — it unlocks from real discovery calls, not from more analysis.
- [ ] Just note it as open; revisit once we've held real US discovery calls.

### 3c. Numbers still marked TBD (can't pitch without them)
- [ ] **Guarantee X / Y** ("pay nothing until we book X consults in Y weeks") — still blank.
- [ ] **Retainer pricing** — still blank, both India and US.
- [ ] These unlock from discovery (§3b), not from more analysis. Note them as downstream of §3b.

### 3d. Open builds with no status
- [ ] **Website still not built.** This is the front door for every outreach motion. Who owns it, and what's the date?
- [ ] **No update from Mayank on the builds** — the India connection build and the ecom connection build. How are they going? Need a real status on each: where they are, what's blocking, when they move.

### 3e. Shubham — new KPIs + what he's actually doing
- [ ] Zero contact from Shubham this week, and he has no KPIs he's accountable for (see §2). Need a straight answer today: **what is he actually doing?**
- [ ] Set his new KPIs live and put them in the §2 table. Whatever he owns, it gets a daily number in the group like everyone else, so this isn't invisible again.

### 3f. Stale docs — fixed
- [x] `shared/context/playbooks/` migrated off the old beauty-DTC positioning to the coaching / test-prep niche (`outbound-playbook.md` examples updated; the other playbooks were already clean).
- [x] Instantly channel copy — already updated.
- [x] Upwork — deprioritized, not in active use anymore, so left as-is.
- [ ] `README.md` is still generic (describes DivineCore as an internal AIOS, no mention of the coaching niche). Minor — leave unless we want the repo front page to state the niche.

### 3g. Equity flag — the "new co-founder" who only edits video
- [ ] There's a new person being floated as a **co-founder** who, as far as I can tell, is **only going to do video editing.**
- [ ] **Pang's position: I am completely not OK sharing any equity with him if video editing is all he does.** Editing is a paid/contract role, not a founder stake. Need to settle this before anyone is called a co-founder or promised equity.

---

## 4. Update from Pang's side

**What I've been doing: hitting my daily KPI, hard.** Up to **60 cold calls today**, aiming for **80 tomorrow** — it's doable but genuinely exhausting, that volume is brutal to sustain.

**Posts are now systemized.** I have a system that tracks every post I put out and whether it performed or not, and I write new posts off the back of the old ones that are doing well — so the content is data-driven now, not guesswork (`/log-post` + `/social-review` + the LinkedIn importer).

**Infra that shipped to run the US dialing motion:**
- **Leads CRM + KPI dashboard on Supabase** (`/crm`) — persists the prospect pipeline and the daily KPI counters.
- **Stats & History** rebuilt around **daily-completion**, not vanity counts — measures whether the non-negotiables actually got done.
- **Cold Call Dialer** — imports US lead CSVs, sorts phones by time zone into morning/night calling blocks, logs dispositions, schedules follow-ups. Folded into `/crm` (API under `/crm/api/dialer`).

**Platform decision (06-10) — for Shubham:** we were going to build everything on **GoHighLevel**, but we decided **not to** and to build it ourselves instead (Twilio + Systeme.io / client-CRM + Claude). Mayank's Sharon rebuttal killed the GHL speed case (the A2P / Google Business waits are identical either way). Shubham — if you have any thoughts on this, share them with us.

**Reliable Medicare — still in their court.** They're still checking through everything. They haven't said anything about the price yet, or about the new updates. Nothing to action on our side until they come back.

**What I'm blocked on / need from you:**
- [ ] Clarity on the US offer (§3a) so I'm dialing leads with the right pitch.
- [ ] LinkedIn connection-request bottleneck — still capping the cold-DM pipeline.

---

## 5. Decisions we don't leave without

- [ ] Goals confirmed or adjusted (§1)
- [ ] Every KPI marked hit/miss with a named blocker (§2)
- [ ] Shubham's new KPIs set and put in the §2 table (§2 / §3e)
- [ ] US offer confirmed: reviews / referrals / review replies + content-machine add-on (§3a)
- [ ] Status pulled from Mayank on the builds + website owner/date set (§3d)
- [ ] Shubham gives a straight status: what is he actually doing? (§3e)
- [ ] Equity question settled: no founder stake for a video-editing-only role (§3g)
