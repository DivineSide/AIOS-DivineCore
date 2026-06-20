# DivineSide — Product Details

Products for education & coaching businesses. Two tracks: **Educational Content** and
**Marketing**. Output is generated in the client's own template, font, and branding.

---

## Track 1 — Educational Content

One input (exam paper, topic, or question set) → branded, print-ready output in minutes.

- **Question paper generation** — original, exam-level questions from web search + uploaded
  PDFs, calibrated and recycled from previous-year papers (PYQs). Output: Word paper in the
  client's format + answer-key page.
- **Educational material (PPT / DOC / any format)** — class slides, study material, notes.
  In-class PPT renders the paper as slides (questions only, no answers).
- **Answer key with full solutions** — for brand-new papers with no official key yet,
  step-by-step worked solutions generated in minutes. Output: teacher solution doc.

---

## Track 2 — Marketing

- **Post & poster generation** — social-media posts and public posters in the client's brand
  style (batch, course, schedule/topic posters).
- **Review collection** — automated request + collect over SMS and email; routes replies.
- **Referral system** — captures and routes referrals from the student/parent base.
- **Cold outreach to students (email + WhatsApp) — *in build*** — outreach engine targeting
  students. WhatsApp for India and other WhatsApp-major markets; email elsewhere.
  - **Open challenge:** no "Apollo for students" exists — no source of student
    contact/intent data. The engine has no list to run on without it.
  - **Direction:** build the data source ourselves — a student-data layer (contacts +
    intent: exam, stage, region) as the targeting spine.

---

## How it works

- One entry point (`run_pipeline.py`) with a hard input gate → emits all artifacts.
- **Generators are pure Python** (`build_paper.py`, `build_deck.py`, `build_solution.py`,
  `build_answer_key.py`, `build_poster.py`) — zero API calls.
- **AI is used only** to read the paper (vision), reason out + verify answers, write the
  reasons, and generate questions from PYQs. ~$0.15–0.20 per 100-question paper.
- **Kruti Dev 010 support** — bidirectional Unicode↔KrutiDev converter to read and write the
  client's legacy Hindi font.

## Answer verification

- Reasoning/maths: self-verified (worked solution is the proof).
- Factual: double-confirmed against two sources; disagreement → flagged for manual check.
- Flags appear in the teacher doc only, never on student-facing material.

## Status

- Manual run via Claude Code. No UI, hosting, or deployment yet.
- Proven end-to-end on a real 100-question UKSSSC paper (Hindi).

---

*Source: `clients/target-academy/` (`pang-product-briefing.md`, `brain/`, `pipeline/`) and
`review-system/`.*
