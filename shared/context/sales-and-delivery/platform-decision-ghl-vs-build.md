# Platform Decision: GoHighLevel vs Build It Ourselves

> **Status: REVERSED (2026-06-10) — building it ourselves, NOT GHL.** Pang's first lean was hybrid-GHL (below). Mayank rebutted with client-specific (Sharon) evidence that defeats the GHL case for this narrow offer — see §10. Resolved direction: **build on Twilio + Systeme.io (or the client's existing CRM) + Claude, owned end to end.** Two guardrails attached (§10): timebox the build to the A2P/GBP wait window, and configure Twilio Advanced Opt-Out (STOP/TCPA) from day one. The §1-9 GHL analysis below is kept as the record of the reasoning; §10 is the current decision.

Author: Pang. Date: 2026-06-10.

---

## 1. The question, stated plainly

For the reviews + referrals + review-reply offer (Pang's US track), do we:

- **(A)** Build the delivery infrastructure ourselves (our own SMS sending, email, CRM, contact import, payment tracking, integrations), orchestrated with n8n + Claude, OR
- **(B)** Rent GoHighLevel as the infrastructure layer and build only our differentiator (the AI conversation) on top of it, OR
- **(C)** A hybrid: GHL for the plumbing, Claude (via webhook) for the intelligence.

Short answer this doc argues for: **(C) — GHL now, harvest our own platform later.**

---

## 2. What "build it ourselves" actually means (the real cost)

This is not "send a few texts with an API." To match what GHL gives on day one we would have to build and maintain:

| Capability | What it takes to build | GHL gives it |
|---|---|---|
| SMS sending (US) | Twilio integration + **A2P 10DLC registration per client** (unavoidable either way) + delivery/retry handling | ✅ built in, guided A2P flow |
| Email sending | Deliverability, domain warmup, subdomain setup, unsubscribe handling, spam avoidance | ✅ built in |
| Contact / CRM data import | Pull each client's customer list from QuickBooks, Square, their booking tool, or CSV; keep syncing new ones | ✅ 40+ integrations (CRM connector) + CSV import |
| Conversation tracking | Store every reply, thread it, know who replied what and when | ✅ native conversations + reply triggers |
| Google review link + reply | Connect each client's Google Business Profile via Google's API, post replies | ✅ native GBP integration |
| Payment tracking | Stripe recurring billing, know when a client of our client pays | ✅ native Stripe |
| Review widgets / social posting | Embed reviews on client sites, auto-post 5-star reviews | ✅ built in |

Every one of these is a thing that **breaks, needs monitoring, and needs a human when an API changes.** Pang's own list of worries (what sends the SMS, what if the API breaks, which CRM does the client use, how do we import data, how do we track payments, Stripe/QuickBooks) is exactly the list GHL has already solved. Rebuilding it is months of work before the first client sees a single review.

---

## 3. The argument from our own strategy (the strongest one)

This is the line that should settle it on the call. Our own CLAUDE.md says, repeatedly and deliberately:

> *"We do not design AIOS up front. We earn it from delivery. A pattern enters AIOS only after it shows up across multiple real builds. Conviction is not evidence, delivery is."*

Building our own SMS/CRM/payments platform right now **is designing the platform up front** — the exact thing the strategy tells us not to do. It is premature abstraction with zero validated patterns behind it.

GHL is to this layer what **n8n is to orchestration**: rented infrastructure we stand on, not the product we sell. We already rent n8n, a VPS, Airtable, Supabase. GHL is the same category of decision. The product is never the tool — it is the research, the AI conversation quality, and the closed loop we build on top.

We earn the right to build our own platform in **Phase 2**, once we have run 3-5 real client builds and *know* which pieces repeat. That build is then **paid for by GHL-delivered revenue**, not by burning our runway before we have a single case study.

---

## 4. Mayank's concern, taken seriously

Mayank wants to own the platform, not rent it. That instinct is right *eventually* and wrong *now*. The honest risks of GHL and how we hold them:

- **"We don't own it / lock-in."** True, but at 0 clients we have nothing to lock in yet. The client relationship, the research, and the AI prompts are ours and portable. Migrating off GHL later is a Phase-2 problem we will gladly have (it means we have revenue).
- **"It limits what we can build."** This is the real question, and the answer is no for our offer — see §5. GHL exposes webhooks and a public API, so anything it can't do natively, we do in Claude and call out to it.
- **"It's a commodity SMMA play (the $100/mo reseller crowd)."** The *resellers* are commodity because they ship GHL's generic templates. We are not them. Our differentiator is the AI conversation layer (§5) and the research/closed-loop underneath. Same tool, completely different product. Using GHL does not make us a GHL reseller any more than using AWS makes us a hosting company.

---

## 5. The capability that actually decides it: can GHL do *our* version?

Our edge is **not** generic one-line review requests ("Thanks, here's a link"). It is **conversational, personalized, owner-voice AI that reads the customer's reply and responds intelligently.** The question is whether GHL constrains that. It does not:

- GHL has a **"Customer Replied" trigger** and a **Conversation AI Workflow Action** that sends a message, waits for the reply, and branches on what the customer said. Back-and-forth is native.
- More importantly, GHL workflows can fire a **POST webhook to an external API mid-conversation.** So we route the customer's reply to **our own Claude endpoint**, Claude writes the genuinely conversational, owner-voice response, and we send it back through GHL.

**Division of labor:**
- **GHL owns:** sending/receiving SMS + email, A2P, contact storage, CRM sync, Google Business Profile connection, payment, review widgets.
- **Claude owns:** reading replies, deciding the next message, writing every message in the owner's voice, the feedback-first logic, the referral ask, the review reply.

This is the best of both: we never rebuild plumbing, and we are never stuck with GHL's generic copy. Our product lives in the layer GHL can't touch.

---

## 6. A2P 10DLC — a fact both options share

Heads up for the call so it's not a surprise: any automated SMS to US numbers requires **A2P 10DLC registration** (carrier rule, via The Campaign Registry). Each client registers their brand with their **EIN**; approval is **3-7 business days**, small fees. This is true whether we use GHL or build on Twilio — it is **not** a reason to pick one over the other. GHL just gives a guided form for it. It becomes a standard per-client onboarding step we run during week 1.

---

## 7. Compliance note on the raffle / incentive (so we get it right once)

Pang's flow: no reply → direct ask → "leave a review, send a screenshot, we enter you in a raffle to win X." The mechanic is good. One fix: **Google prohibits incentivized reviews**, and tying the raffle to *leaving the public review* gets reviews filtered or removed.

Compliant version that keeps the exact same UX:
- Frame the raffle entry as reward for **sharing feedback / a screenshot of their experience**, not for the public 5-star review specifically.
- Everyone who engages with the feedback ask gets entered; the happy ones then get the (non-incentivized) "would you mind posting that on Google?" ask.
- Same screenshot step, same raffle, same conversion — just never word it as "review = raffle entry."

**Raffle prizes by business type** (high perceived value, near-zero marginal cost):
- Test prep / tutoring centers: free 1:1 session, a free full-length mock exam, a free month.
- College admissions consultants: free essay-review session, a 30-min strategy call, an Amazon / college-bookstore gift card.
- Career / parent-student coaches: free session, a resource bundle, gift card.

---

## 8. Recommendation

**Adopt GoHighLevel as the infrastructure layer (option C). Build the AI conversation layer in Claude, connected via webhook. Do not build our own platform now.**

Why this wins:
1. **Speed.** We can onboard a hot lead and show real reviews this week, not in three months.
2. **Cost.** ~$100-300/mo per sub-account vs months of our own dev time before a single result.
3. **Strategy-aligned.** Rent the plumbing, harvest the platform later — exactly what CLAUDE.md tells us to do.
4. **No ceiling on our edge.** The webhook + Claude setup means GHL's generic copy never limits us.
5. **Upsell surface.** GHL bundles social posting, review widgets, missed-call text-back, etc. — more we can sell the same client later without building it.

What we revisit and when:
- **Phase 2** (after 3-5 builds): if specific patterns clearly repeat and GHL is genuinely constraining them or the per-client cost stops making sense, *then* we scope our own platform — paid for by GHL-era revenue, designed from validated patterns instead of guesses.

---

## 9. Decision log

- **Pang's first lean (2026-06-10, superseded):** Hybrid GHL + Claude webhook.
- **REVERSED, resolved direction (2026-06-10):** Build it ourselves — Twilio + Systeme.io (or client's existing CRM) + Claude. Mayank's Sharon-specific rebuttal (§10) defeated the GHL speed argument. Owned end to end, no $100-300/mo/client overhead for unused CRM breadth.
- **Conditions:** (1) timebox the build to the A2P + GBP approval window (~1 week of otherwise-dead time); (2) configure Twilio Advanced Opt-Out (STOP/UNSTOP/HELP) + timezone quiet-hours from day one — this is the one compliance job GHL used to absorb.
- **Reconsider GHL only if:** we scale past ~5-10 concurrent clients and per-client maintenance/on-call becomes the bottleneck, or we start selling the full-CRM breadth GHL is actually built for.
- **First client:** Sharon (the build is being scoped against her actual flow — course-end review trigger, upfront payment so no payment tracking needed).

## 10. Mayank's rebuttal and the reversal (2026-06-10)

After working the actual blockers with Sharon, Mayank argued against GHL. The points that hold:

- **The speed argument was illusory.** The real bottlenecks are A2P 10DLC (3-7 days) and GBP verification (3-7 days). Both waits are identical whether we use GHL or Twilio directly — GHL just wraps the same forms/OAuth. So the build happens *during* the unavoidable approval wait, at no net time cost. This defeats the §8 "speed" case.
- **GHL's inbuilt SMS underdelivers.** From direct client experience, GHL's native LeadConnector numbers failed repeatedly and they ended up wiring Twilio inside GHL anyway. So even on GHL you use Twilio — paying GHL on top buys nothing on the one feature we'd rent it for.
- **GBP "native integration" is just OAuth (10 min); the wait is Google's.** No GHL advantage.
- **Email + CRM don't need GHL.** Systeme.io handles deliverability (DKIM/warmup) out of the box; for contacts we ask the client once where their list lives and import/automate. At one client this is not ongoing complexity.
- **Payment tracking was a mistake in this doc.** Coaching takes payment upfront; the review trigger is course-end (batch completion), not payment. Removed from scope.
- **The math:** GHL ($100-300/mo) is priced for full-CRM breadth (widgets, social posting, pipelines) we are not selling. We'd pay for unused surface that doesn't even shorten the real blockers.

**Two guardrails added on agreement (the things Mayank's "few days" estimate glosses):**
1. **Build estimate realism / timebox.** v1 sending is easy; a reliable, repeatable, multi-client system (retries, conversation state, error handling) is where time hides. Box it to the A2P/GBP wait window; if it isn't reliably sending to a test phone by then, stop polishing.
2. **Compliance is now ours.** STOP/opt-out/TCPA + timezone quiet-hours were handled by GHL. Replicate with **Twilio Messaging Service Advanced Opt-Out** configured day one. With that, we lose nothing GHL provided.

**Resolution:** build it ourselves, owned end to end, under those two guardrails. Aligns with the harvest-don't-design principle *and* the unit economics at this stage.
