# Guarantee — DivineSide

> **⚠️ SUPERSEDED (pre-2026-06-06, beauty DTC).** Niche pivoted to education / coaching. TYPE A/B and the "$500 penalty" mechanic are tied to the retired beauty offer. Do NOT pitch any of it. The guarantee for the new offer is undefined; current posture is proof-first (demo before payment), see [offer.md §05](offer.md). Current niche/audience: [business-info.md](../identity/business-info.md), [audience.md](../identity/audience.md).

> **IN REVIEW until 2026-06-05.** TYPE A / TYPE B guarantee variants with the $500 personal penalty are the **destination** guarantee mechanic. **Current state during the sprint (Phase 1 of the JP-model arc):** custom workflow builds are scoped per-client at kickoff with a written deliverable; the $500-penalty guarantee may or may not survive the productization lock. **Verbatim guarantee paragraphs in this file should NOT be pasted into proposals, Looms, or sales calls until re-validated.** See [`../../../CLAUDE.md` §2](../../../CLAUDE.md) for the Phase 1/2/3 arc, [`offer.md` §00](offer.md) for current operating state, and [`../../../.claude/alignment-2026-05-22.md`](../../../.claude/alignment-2026-05-22.md) for the sprint structure.

> The standardized guarantee that applies to **every channel** Pang/DivineSide sells through: cold email, Upwork, LinkedIn, inbound, warm intro. Attached as a section in every proposal Google Doc, referenced verbally in the Loom and on discovery calls, and formalized inside the SOW.
>
> **Two variants** — TYPE A (hours-saved) and TYPE B (functions-delivered, **default**). Choose based on the JD or prospect; the live classification logic for Upwork specifically lives in [sales_os/integrations/upwork/prompts.py](../../../sales_os/integrations/upwork/prompts.py) and applies the same way for other channels. See §02 for what triggers each.
>
> **Loading discipline** — any agent or human generating proposals, Loom scripts, or discovery calls where this guarantee is offered should load this file.
>
> **Pairs with [offer.md](offer.md)**: `offer.md` is the strategic offer doc (what we sell, pricing anchors, channel audiences, expansion path). This file is the legal-mechanic deep-dive (verbatim guarantee paragraphs, what triggers each variant, what voids the guarantee, claim mechanic). Load both for any agent that drafts proposals or runs sales conversations.

Last updated: 2026-05-17

---

## 01 · The headline

**You don't pay me anything upfront. You only pay when the system is delivered and we've verified it does what we agreed at kickoff. If we miss the target by the end of month two, you don't pay me anything, and I pay you $500 out of my own pocket for the time you committed.**

The "target" depends on which variant applies — see §02.

### Monetary value framing (TYPE A only)

When the variant is TYPE A, the application body and proposal Doc both frame the value in money:

> *"10 hours per week back at a conservative operator rate of $25 per hour is around $1,000 per month — roughly $12,000 per year of your team's capacity redirected from running the business to growing it."*

This is not a literal cash-savings number unless the buyer fires someone. It's the **equivalent value of the time freed up** — capacity the team can spend on growth-driving work. Use $25 as a defensible floor anchor; if the buyer's effective hourly rate is higher (senior ops staff often $40-60/hour), the equivalent value scales.

---

## 02 · The two variants

### TYPE B (functions-delivered, DEFAULT)

Use for the vast majority of JDs. The buyer wants a system with specific features. The deliverable is the value. Also use TYPE B for contractor-for-agency JDs.

**The trigger:** A function listed in the signed kickoff spec doesn't work, works incorrectly, or is missing at the week 8 delivery test.

**Verbatim paragraph** (also baked into [prompts.py](../../../sales_os/integrations/upwork/prompts.py) — `HERE'S MY OFFER` is ALL CAPS, no markdown bold, since Upwork renders plain text):

> HERE'S MY OFFER: if the system you want me to build doesn't perform the functions we agreed at kickoff by the end of week eight, you don't pay me anything, and I pay you $500 out of my own pocket for wasting your time.

### TYPE A (hours-saved)

Use **only** when ALL four signals are present:
1. The JD explicitly mentions saving the buyer's team's hours, freeing up time, or reducing manual work they currently do.
2. The buyer is the operator whose hours would be saved (not a contractor-hire JD).
3. The "hours saved per week" can plausibly be measured against a current baseline.
4. The pain in the JD reads as "I or my team is drowning in this repetitive work."

If any of those four are not clearly true, default to TYPE B.

**The trigger:** The system fails to save the buyer's team at least 10 hours per week by the end of month two.

**Verbatim paragraph** (also baked into [prompts.py](../../../sales_os/integrations/upwork/prompts.py)):

> HERE'S MY OFFER: if the system I build for you doesn't save more than 10 hours per week, either of your time as the founder or your employees' time, by the end of month two, you don't pay me anything, and I pay you $500 out of my own pocket for wasting your time.

---

## 03 · What does NOT trigger the guarantee (both variants)

Regardless of variant, these don't qualify as a delivery failure:

- **"It works, but I don't like how it's set up."** Aesthetic or preference disagreements are not delivery failures. Raise them during the build, not after.
- **"It works, but my team isn't using it."** Adoption is the buyer's responsibility; delivery is mine.
- **"It works, but I want to change what it does."** That's a scope change, not a delivery failure. We can rescope under a new agreement.

**Variant-specific:**
- TYPE B: *"I didn't save the hours I expected"* doesn't qualify. TYPE B's contract is the function spec, not an hours metric.
- TYPE A: subjective dissatisfaction with how time was redirected doesn't qualify. The trigger is the hours-saved number, measured against the baseline agreed at kickoff.

---

## 04 · The two phases

### Step 1 · Kickoff agreement (week 1)

We jointly write a 1-page spec of the workflow:

- What the workflow does — functions, inputs, outputs
- The manual function(s) it replaces
- **TYPE A only:** the estimated hours per week the team gets back (must be ≥ 10), plus a baseline log of how long the function currently takes
- Tools and integrations required
- Access I need from the buyer to build (API keys, accounts, tool access)

Both parties sign off on the spec before I write a single line of code.

### Step 2 · Delivery test

Timing depends on the variant:
- **TYPE B — week 8.** I demonstrate the system end-to-end against the spec, function by function.
- **TYPE A — end of month two.** We measure hours saved per week against the kickoff estimate and the pre-build baseline.

If the variant's target is met → buyer pays the agreed fee. If not → no payment + $500 paid from my pocket as a make-good.

---

## 05 · Buyer obligations

For the guarantee to remain in effect, the buyer commits to:

- Provide access to the tools agreed on (Shopify, Klaviyo, Meta Ads, GoHighLevel, etc.) by end of week 1.
- Respond to my questions about their business and workflow within 2 business days during the build.
- Sign off on the week 1 spec before building begins.
- (TYPE A only) Establish the pre-build hours baseline by end of week 1 — typically a log of how long the function currently takes and how often it runs.

---

## 06 · What voids the guarantee

- **Scope changes mid-build.** We can rescope, but the timeline resets from the rescope date.
- **Tool access not provided by end of week 1.** The deadline shifts by however many days access was delayed.
- **Spec not signed off.** No signed spec = no guarantee in effect.
- (TYPE A only) **Baseline not established.** Without a pre-build hours baseline, the hours-saved target can't be verified.

---

## 07 · Claim mechanic

If the variant's target is missed at the delivery test:

1. Buyer notifies me within **7 days** of the delivery test.
2. We jointly walk through the failed target — for TYPE B, the function checklist; for TYPE A, the baseline log vs. post-build measurement.
3. Since no payment was made upfront, there's nothing to refund — the unpaid fee is written off.
4. $500 paid separately within 7 days of the claim.

Past the 7-day claim window with no notification, the guarantee is closed and the fee becomes due as normal.

---

## 08 · Where this gets referenced

- **Loom video (Upwork)** — verbal mention of the guarantee in the offer section, ~30 sec. Phrasing locked in [`../playbooks/upwork-loom-script.md`](../playbooks/upwork-loom-script.md) §1:30–2:15.
- **Upwork application body** — verbatim TYPE A or TYPE B paragraph (from [`prompts.py`](../../../sales_os/integrations/upwork/prompts.py)) appears between the hook line and the "I'm the person you're looking for" paragraph.
- **Proposal Google Doc (Upwork)** — the `{{offer}}` placeholder is filled by `proposal_fields` with the same verbatim paragraph (the TYPE A version includes the dollar math at the top).
- **Cold email / LinkedIn DMs / discovery calls** — the guarantee is delivered verbally on the call or as a closing line in the 24h audit doc. Same wording; pick TYPE A or TYPE B by the four-signal test in §02.
- **SOW / contract** — referenced in the scope description on the platform the deal closes through (Upwork escrow, Stripe invoice, signed contract, etc.).

---

## 09 · What this doc is, what it isn't

**It is:**
- The standardized guarantee mechanic for **every channel** DivineSide sells through.
- A reference doc agents (Upwork pipeline, future Sales OS module) load when drafting proposals.
- The source of truth for the *meaning* of the guarantee and the conditions around it. The verbatim phrasing lives in [prompts.py](../../../sales_os/integrations/upwork/prompts.py); this doc explains what the words actually commit Pang to.

**It isn't:**
- The strategic offer doc. That's [`offer.md`](offer.md). It covers pricing anchors, payment model, channel audiences, scope envelope, expansion path — the *what* and the *how much*. This file covers *how the guarantee actually works as a legal mechanic*.
- A legal contract on its own. The terms here get formalized inside the SOW (Upwork escrow, Stripe invoice, signed contract) when a deal closes.

---

## 10 · Lessons

*(Add a one-liner per project where this guarantee was offered. Was a claim made? What was the spec dispute, if any? What would you change for the next project?)*
