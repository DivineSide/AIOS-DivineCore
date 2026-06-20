# Format Conventions — PPT + Question Paper

> ⏳ To be extracted from his real materials once they arrive (resource-request items 1–2). Extracted, never invented.

## PPT
- **Font: Kruti Dev (owner preference, per Mayank 2026-06-11).** ⚠️ Kruti Dev is a **legacy non-Unicode font** — Devanagari glyphs mapped onto ASCII codepoints. Two pipeline consequences:
  1. `deck.py`/`paper.py` must convert LLM output (Unicode Devanagari) → Kruti Dev encoding before setting the font, or the text renders as garbage. Solved problem (public mapping tables exist); needs a `unicode_to_krutidev()` util + tests for conjuncts/matras/reph reordering.
  2. `ingest.py` must convert the **other direction** — his existing PPTs/papers typed in Kruti Dev will extract as gibberish ASCII; KrutiDev→Unicode conversion is required before the corpus is usable for grounding.
  - **Variant confirmed: Kruti Dev 010** (Aryan, WhatsApp 2026-06-11 — "10 wala"). Still verify his actual files on arrival in case some material is Unicode/Mangal mixed.
  - Kruti Dev is NOT installed on Mayank's machine yet — install (free) before judging rendering.
- Template / colors: ⚠️ "PPT FRONT.pptx" received 2026-06-11 is a single slide with **zero text runs** (pure graphics — branded cover). No usable template/font info. **Gap: need one real lesson PPT from the staffer.**
- Slide structure (title, content density, examples, recap?): ⏳ blocked on a real lesson PPT
- Language register: ✅ all Hindi; English only for a few paper headlines + institute name

## Materials received 2026-06-11 (in `resources/`, gitignored)
- 5× revision-series papers (.docx, ~700–830 paragraphs each): body text overwhelmingly **Kruti Dev 010** (1.2k–4.6k runs/file), with Palatino Linotype / Times New Roman / Calibri for English fragments. Question format: statement-based MCQs ("निम्नलिखित कथनों पर विचार कीजिए…") with 4 options, 100 marks/paper.
- Converter verified against real file text — clean output incl. nuktas (करोड़), conjuncts, numbers, parens.
- **Ingest lesson #1:** DOCX runs fragment mid-word (e.g. `fuEufyf` + `[kr` split across runs) — positional Kruti rules (chhoti-i, reph) break if converted per-run. **Join run texts per paragraph (per font-class) BEFORE k2u conversion.**
- **Ingest lesson #2:** source typos exist (e.g. `lnaHkZ` = सदंर्भ, sic) — convert faithfully, never "fix" exam content silently.

## Question paper
- Sections, marks distribution, difficulty mix: ⏳
- Instruction text (verbatim from his papers): ⏳
- Answer key format: ⏳
