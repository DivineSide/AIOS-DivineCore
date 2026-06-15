# Case Studies

> **CURRENT NICHE FLAGSHIP:** the **Target Academy** block below (education/coaching, added 2026-06-15) is the live build for the new niche and is **NOT** superseded. The beauty-era blocks beneath it (OuterSignal, Cracked.ai, Reading Rhythms, Reliable Medicare) stay valid as Pang's prior credentials; only their positioning is pre-pivot.

> **⚠️ Beauty-DTC blocks below are pre-2026-06-06.** Niche pivoted to education / coaching. The real past-client numbers (Reliable Medicare, Cracked.ai, etc.) stay valid as Pang's credentials, but the framing/positioning is beauty-era and not yet migrated. Current niche/audience/offer: [business-info.md](../identity/business-info.md), [audience.md](../identity/audience.md), [offer.md](offer.md).

> **Canonical record of shipped client work.** Loaded by any agent or human generating sales content (Upwork applications, proposal docs, LinkedIn posts, DMs, discovery-call follow-ups). Update here first, then propagate framing changes to [`../identity/pang.md`](../identity/pang.md) and [`../../../sales_os/integrations/upwork/about_me.py`](../../../sales_os/integrations/upwork/about_me.py). Note: Target Academy is a **DivineSide team build** (Mayank-run), not Pang's solo work, so it propagates to company-facing copy, not Pang's personal Upwork credentials.

---

## Target Academy — the content engine (FLAGSHIP, education niche)

> **Status: live production testing (as of 2026-06-15).** Built, tested end-to-end on a real paper, run **done-for-you** by DivineSide from Mayank's machine. No UI, hosting, or self-serve yet — by design, until a week of real client use is in. Not pushed to repo yet (pushing after live testing). Do not pitch a dashboard or self-serve app.

**Industry:** Education / coaching. 8-year govt-exam-prep institute in India (UKSSSC — Patwari, Lekhpal, VDO). The beachhead client and our distribution channel (50+ same-niche connections).

**The pain (owner's #1, unprompted):** making study content by hand. ~2 hours per class PPT plus a separate approval person, totalling 10+ hours/week of pure typing-and-formatting labor.

**Build — a content engine.** One input (an existing past paper, even a photo of one, *or* just a topic) produces three artifacts, all in the institute's exact template, font, and branding (their real files are the base, so borders/watermark/branding are inherited, not imitated):

- **In-class PPT** — the questions as slides, verbatim MCQs, no answers. Shown live in class.
- **Teacher solution doc** — every answer plus a one-line reason; full worked steps for maths/reasoning. Teacher-only.
- **Branded practice paper** — full Word paper in their format with an answer-key page (उत्तरमाला). Exported to PDF, sent to students.

A **marketing-poster generator** (batch/course posters in their style) is the second workflow the owner is already pulling for.

**How it works (the economics).** Almost none of it is AI. One small, surgical AI step reads the paper (vision, for image-PDFs), reasons out and verifies answers, writes the one-line reasons, and can generate original questions from previous-year papers — producing one structured questions file. Three pure-Python generators then format that file into the three artifacts at **zero API cost**. The only metered cost is the AI step, roughly **$0.15–0.20 per 100-question paper**; formatting is free and instant. A bidirectional converter for **Kruti Dev 010** (a legacy non-Unicode Hindi font) lets us both read the institute's existing files and write output in their exact font — generic AI tools output Unicode and render as garbage in their template.

**The trust gate (the answer to "AI makes mistakes").** For a brand-new paper with no official key out, every answer is cross-checked against two reliable sources (ExamPillar + Testbook). Both agree, it ships marked confirmed. They disagree, only one has it, or it's tricky, it is flagged for manual check before anything reaches the class. Maths/reasoning answers carry a full worked solution, so they self-verify. **Flags live in the teacher doc only, never on student-facing material.** The machine does the labor; the human still supervises.

**Proof:** run end-to-end on a real UKSSSC Patwari paper (100 questions, Hindi) — all three files generated clean. Live path (a brand-new paper photographed → read → generated) and garbage-input cases both stress-tested. The owner saw the demo and committed to buy ("anybody will buy this — you're my first customer for sure").

**Outcome (stated, pre-revenue — do not cite as a measured post-build metric yet):**
- Replaces the owner's 10+ hrs/week of manual content prep (~2 hrs per PPT) with minutes of done-for-you turnaround
- Beachhead owner converted from demo to committed buyer; 50+ same-niche connections as warm distribution

**Why it travels (US/UK):** education businesses everywhere run on content. The delivery shape changes per market (a US test-prep worksheet ≠ a UKSSSC PPT), but the engine is the same — content need in, branded verified output out. The format and input layers are configurable; the core is universal. PPT/docx are Target Academy's formats, an example not a fixed output — always ask a prospect what format they deliver material in and swap the templates.

**Tech:** Anthropic API (the AI layer only), python-pptx, python-docx, custom Kruti Dev ↔ Unicode converter. Orchestrated by a single entry point with a hard input gate.

---

## OuterSignal

**Industry:** SaaS
**Build:** End-to-end CRM automation. Fully automated lead-to-deal pipeline. The system runs the flow end-to-end; the team supervises.

**Outcome:**
- ~10 hours/week saved

**Tech stack:** n8n, Airtable, Instantly, NeverBounce

---

## Cracked.ai

**Industry:** SaaS (AI), Los Angeles
**Build:** End-to-end AI-generated content pipeline across TikTok, Instagram, and YouTube. Idea, script, asset generation, scheduling and posting all run by the system.

**Outcome:**
- 20 posts/week
- 1,300+ pieces of content shipped to date

**Tech stack:** n8n, Airtable, SORA, Creatomate

---

## Reading Rhythms

**Industry:** Community
**Build:** Cold-email lead generation system. Apollo sourcing, enrichment, qualification, send, reply triage.

**Outcome:**
- 8% reply rate
- 5 positive replies in 1 month (3% positive reply rate)

**Tech stack:** n8n, Instantly, NeverBounce, Apollo

---

## Reliable Medicare

> ⚠️ Currently the prospect for the RM 365 proposal. Frame as Phase 2 / existing relationship when relevant; do not cite as an external case study back to them.

**Industry:** E-commerce, healthcare. UK, ships to 150+ countries.
**Scale:** £2.23M net assets, 2,800+ Trustpilot reviews.
**Build:** Consulted on how AI could streamline operations, then built the systems directly.

**Outcome:**
- 10+ hours/week saved

---

## How to use this file

- **Proposal docs / case-study sections** → pull a full block (the H2 plus all bullets).
- **One-line credibility plugs (Upwork application body, LinkedIn About, cold-email signature)** → use the condensed bullets in [`../identity/pang.md`](../identity/pang.md) §"Who You Are" and [`../../../sales_os/integrations/upwork/about_me.py`](../../../sales_os/integrations/upwork/about_me.py), which mirror this file in shorter form.
- **Discovery-call references** → cite the one whose domain matches the prospect's. Stay specific to the numbers above. Do not invent metrics.
