# Workflow Spec — Content Automation v1

**What it does:** given a topic from an active batch's syllabus, produce (1) a print-ready PPT in the institute's own template and (2) a question paper with answer key in the institute's own format — factually grounded in the institute's source materials, with a built-in human QC step before anything reaches the client.

**What it does NOT do (v1):** study-material handouts, auto-notes (rejected in discovery), app integration, scheduled/autonomous runs, anything ungrounded in the corpus.

**Inputs:** topic (+ batch), `corpus/parsed/` (his materials + source books), `templates/` (his PPT template + style spec), `brain/format-conventions.md`.
**Outputs:** `review/<topic>/deck.pptx` + `review/<topic>/paper.pdf` (+ answer key) → human QC → `outputs/`.

**Success criterion:** the owner's team judges a side-by-side of our deck + paper vs their own (2–3 already-produced topics) as approved-quality, with zero factual errors against source — and total turnaround (generation + QC) is a fraction of their current per-deck/per-paper hours (baseline captured via the resource-request queries).

**Edge cases to handle:** bilingual/Hindi content and Devanagari rendering in PPTX (Phase-1 spike), topics thin in the corpus (pipeline must say "insufficient source material" instead of inventing), template elements python-pptx can't reproduce (flag, don't approximate silently).

**Business gate:** demo on a real upcoming class → trial period with the success check above → retainer conversation (pricing only at that point).
