---
name: run-pipeline
description: Run the Target Academy content pipeline — turn a solved questions paper into the branded in-class PPT, the teacher solution doc, and the branded practice paper. Use when the user says "run the pipeline", drops an exam paper to process, or asks to generate the class deck + solution for a paper.
---

# Run Pipeline — Target Academy Content Workflow

Turns ONE solved questions paper into three deliverables, in the client's exact
template, with a built-in answer-verification gate. This is the production
workflow that was demoed to the owner and locked 2026-06-11.

## The hard gate (do not bypass)

**The pipeline does not start until exactly one valid questions JSON is sitting
in `clients/target-academy/review/input/`.** `run_pipeline.py` enforces
this — empty folder, multiple files, or a malformed/short JSON all refuse with a
clear message. Your job before running is to PRODUCE that JSON correctly.

## Inputs you may be handed

- A **PYQ** (previous-year paper) — HTML in `resources/pyq/` (plain text, parse
  directly) or an image PDF (render with PyMuPDF/`fitz` at dpi=150, then vision-read).
  PYQs carry the commission's **official answer key** → ground truth.
- A **live/new paper** (PDF or photos) — no official key yet. You must determine
  and verify every answer (see Answer Verification below).

## Steps

1. **Build the questions JSON** into `review/input/<name>.json`. Per-question shape:
   `{ "n", "stem", "options":[...], "answer":"a".."e", "reason"?, "solution"?,
   "sources"?:[...], "flag"?, "image"?, "option_images"?:[...], "long_options"? }`.
   Top-level: `filename`, `ppt_filename`, `solution_filename`,
   `answer_key_filename` (client-facing names), `title_hindi`, `subtitle_hindi`,
   `solution_title`, `solution_subtitle`, and — for PYQs only —
   `"answer_source": "official_key"`.
   - Transcribe Hindi **verbatim**. Keep all options exactly as printed. The paper
     is bilingual (English left / Hindi right) — use the **Hindi** version.
   - `reason`: one-line संकेत for factual questions. `solution`: full worked हल
     for maths/reasoning (self-verifying — no external source needed).
   - **Diagram questions** (reasoning/maths with figures that can't be retyped):
     keep the text parts as branded text, crop the diagram parts verbatim with
     `crop_figure.crop(page_png, (l,t,r,b), out_png)` into `review/input/crops/`.
     Use `"image"` for a question's own figure; `"option_images": [...]` when the
     (a)-(d) OPTIONS are themselves diagrams (crop each one). The gate refuses to
     run if any referenced crop file is missing.

2. **Answer Verification — by question TYPE (live papers only; skip for official-key PYQs):**
   - **Reasoning / simple maths → SELF-VERIFIED.** Work the steps, put them in
     `solution`. No external source needed — a correct worked solution IS the
     proof. The pipeline treats any question with `solution` as unflagged.
   - **Factual questions → two-source confirmation, TOPIC-AWARE.** Determine the
     answer, then confirm against the right tier for the topic:
     - **National GK** (Indian polity/history/geography/science/current affairs):
       Tier-1 = **Testbook + ExamPillar**. Tier-2 = Adda247; NCERT corpus.
     - **Uttarakhand-specific GK** (UK history/geography/culture/schemes/people —
       ~40-50% of a UKSSSC paper): Tier-1 = **ExamPillar (UK section) + one UK
       site** (uttarakhandexamsgk.com / studyfry.com / gktoday.in UK quiz).
       Tier-2 = B.S. Negi / उत्तराखंड परीक्षावाणी corpus; a second UK site.
       (National sources are thin on UK-specific facts — don't rely on them here.)
   - Both Tier-1 agree → set `"sources": ["exampillar","testbook"]` (or the UK
     pair) → green ✔ in the solution doc. One/disagree/none → leave a single
     source or set `"flag": "<why>"` → RED ⚠ for Mayank's check.
   - PIB / india.gov.in are for current-affairs *facts*, NOT answer keys.
   - **Never auto-ship** a one-source answer, a sources-disagree answer, or a
     tricky "उपर्युक्त में से कोई नहीं" correct answer — flag for Mayank's check.

3. **Run it:** `python clients/target-academy/pipeline/run_pipeline.py`
   (consumes the one file in `review/input/`). Outputs land in `review/output/`:
   - `<name> (Class).pptx` — branded in-class deck, **verbatim MCQs, NO answers**
   - `<name> - Solution (Teacher).docx` — answers + reasoning + ⚠ flags
     (**source provenance and flags live HERE ONLY — never on branded artifacts**)
   - `<name>.docx` — branded practice paper with उत्तरमाला answer key
   - `<name> - Answer Key.pdf` — simple one-page answer key (owner request)
   - NOTE: close any of these if open in Word/PowerPoint, or the write fails
     with PermissionError (file lock, not a bug).

4. **Report** the run summary: questions count, and which Q numbers (if any) are
   flagged for Mayank's manual check before anything reaches Aryan/the class.

## Discipline (from CLAUDE.md + brain/decisions.md)

- Manual via Claude Code — **no deployment/hosting/productization** until Mayank
  says so. Generation currently runs on plan usage; the Anthropic API key is
  reserved for the productization step (it does the same vision/reasoning work).
- Flags and source lines appear in the **teacher solution doc only** — the
  in-class PPT and branded paper carry no review marks.
- Repo is PUBLIC: outputs and inputs stay in the gitignored `review/`.
- Every owner correction → a line in `clients/target-academy/brain/decisions.md`.
