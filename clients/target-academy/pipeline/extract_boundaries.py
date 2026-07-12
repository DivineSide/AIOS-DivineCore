# -*- coding: utf-8 -*-
"""Pass 1 of the two-pass extractor: the INTELLIGENCE pass.

The model does the ONE thing that genuinely needs intelligence — decide where
each question begins and ends — and NOTHING else. It reads the whole flat OCR
text (line-numbered) and returns only boundaries + a confidence, never the
question CONTENT:

    [{"n":1, "start_line":40, "end_line":47, "n_options":4, "confidence":"high"}]

Why this shape:
  * Output is ~10 tokens/question (vs ~150 when it re-emits stem+options), so a
    100-question paper is ~1k output tokens — nowhere near any cap. Truncation,
    the failure the old recursive-split machinery existed to handle, becomes
    STRUCTURALLY IMPOSSIBLE. No splitting, no merge-across-splits, no lost
    boundary questions.
  * The model never rewrites text, so it cannot introduce a spelling error. Pass
    2 (slice_questions) copies the exact source lines. Spelling is now purely an
    OCR-quality concern, handled by the guarded proofread stage, not here.
  * Feeding the whole document as one line stream (NOT per page) dissolves the
    "a question's options span a page break" edge case — a page seam is just
    more lines; the model sees Q40's 4th option wherever it physically is.

The boundary list is cross-checked against the existing, battle-tested
`_estimate_question_count()` (handles zero-width-hidden numbers, Kruti-Dev
danda-as-dash, markdown prefixes). A large disagreement is a signal to re-ask.
"""
from __future__ import annotations

import json
import re

from llm import complete, parse_json
# Reuse the hardened deterministic question counter — do NOT write a new one.
from extract_docx import _estimate_question_count


# The intelligence pass is worth the smart tier: getting boundaries right is the
# whole game, and output is tiny so the smart model's higher output price barely
# matters (~1k output tokens for a full paper).
_BOUNDARY_MODEL = "smart"
# Output budget: ~10 tokens/question, so even a 200-question paper fits easily.
# Generous headroom; boundaries never truncate at this size.
_BOUNDARY_MAX_TOKENS = 8_000


_SYSTEM = """You segment an Indian competitive-exam MCQ paper. The text below is
the paper's OCR output with EVERY line prefixed by its line number in [brackets].

Your ONLY job is to mark where each multiple-choice question begins and ends.
Do NOT return the question text or the options text — only line numbers.

Return ONLY a JSON array, no prose, no markdown fences:
[{"n":1,"start_line":12,"end_line":18,"n_options":4,"confidence":"high"}]

For each question:
- "n": the question's printed number (integer). If unnumbered, count 1,2,3…
- "start_line": the line number where the question's stem BEGINS.
- "end_line": the line number of the question's LAST option (inclusive). This is
  usually just before the next question's start_line — but a question's options
  can continue across what looks like a page break, so include ALL of its
  options even if they are far below the stem.
- "n_options": how many answer choices (a/b/c/d…) this question has. Almost
  always 4. If you can only clearly see fewer, report the real number AND set
  confidence to "low" — do NOT invent options to reach 4.
- "confidence": "high" if the question's full stem and all its options are
  clearly readable; "low" if any part is blurry, cut off, missing, or you are
  unsure where an option is. Be honest — "low" triggers a careful re-read, it is
  not a failure.

Rules:
- Cover EVERY question in order. Do not skip, merge, or split questions.
- Ranges must not overlap and must be in ascending order.
- Never guess content you cannot read — that is what "low" confidence is for."""


_RETRY_SYSTEM = """You are RE-READING a small region of an exam paper to fix a
boundary mistake. The text below is line-numbered OCR of ONE question's region.

A previous pass got this question wrong. The specific problem is stated below.
Look again CAREFULLY — the missing option is often on the next line, or a marker
like (d) / (घ) was mis-read so an option was skipped.

Return ONLY a JSON array with the single corrected question, same shape:
[{"n":N,"start_line":S,"end_line":E,"n_options":4,"confidence":"high"}]

- Include ALL four options' lines in the range, even if the 4th is lower down.
- Only set confidence "low" if, after looking carefully, the text is genuinely
  unreadable (blurry/cut-off pixels) — not merely because it was wrong before."""


def number_lines(text: str) -> tuple[list[str], str]:
    """Return (raw_lines, numbered_text). raw_lines[i] is line i+1's content, so
    the model's 1-based line numbers index straight back into it for slicing.
    Blank lines are kept (they carry position) so numbering stays aligned with
    the source the slicer will cut."""
    raw = text.splitlines()
    numbered = "\n".join(f"[{i + 1}] {ln}" for i, ln in enumerate(raw))
    return raw, numbered


def _parse_boundaries(raw_out: str) -> list[dict]:
    s = raw_out.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s).strip()
    try:
        data = parse_json(s)
    except (ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for b in data:
        if not isinstance(b, dict):
            continue
        try:
            start = int(b["start_line"])
            end = int(b["end_line"])
        except (KeyError, TypeError, ValueError):
            continue
        if start < 1 or end < start:
            continue
        out.append({
            "n": b.get("n"),
            "start_line": start,
            "end_line": end,
            "n_options": b.get("n_options"),
            "confidence": (b.get("confidence") or "high").lower(),
        })
    # keep ascending, non-overlapping by start
    out.sort(key=lambda x: x["start_line"])
    return out


def find_boundaries(text: str) -> tuple[list[dict], int]:
    """Pass 1. Return (boundaries, estimated_count).

    `boundaries` is the model's per-question line ranges. `estimated_count` is the
    deterministic cross-check from the paper's own numbering; the caller compares
    the two and re-asks if they disagree beyond a small slack.
    """
    _, numbered = number_lines(text)
    raw = complete(_SYSTEM, numbered, model=_BOUNDARY_MODEL,
                   max_tokens=_BOUNDARY_MAX_TOKENS)
    boundaries = _parse_boundaries(raw)
    estimated = _estimate_question_count(text)
    return boundaries, estimated


def refind_one(region_text: str, n, reason: str) -> dict | None:
    """Informed retry for ONE question. `region_text` is the line-numbered local
    region; `reason` is the exact validation failure fed back to the model so it
    corrects with information rather than re-guessing identically.

    Returns the single corrected boundary dict (line numbers are LOCAL to
    region_text — caller maps them back), or None if unparseable."""
    user = (f"Question {n} was extracted wrong. Problem: {reason}\n\n"
            f"Re-read this region and return the corrected boundary:\n\n{region_text}")
    raw = complete(_RETRY_SYSTEM, user, model=_BOUNDARY_MODEL, max_tokens=1024)
    got = _parse_boundaries(raw)
    return got[0] if got else None


# ── content-read escalation (for MARKER-parse failures, not boundary failures) ──
# When the boundary is correct but the deterministic slicer can't read a garbled
# option marker (e.g. Sarvam turns "(a)" into ";ंद्ध"), re-asking the boundary is
# useless. The narrowest possible fix: hand the model JUST this one question's
# lines and ask ONLY for its options text, verbatim. Tiny (~50 tok), rare (~1% of
# questions). The stem is NOT re-read (it was fine) — only the options the slicer
# fumbled — so this cannot rewrite the question, only recover choices the OCR
# garbled the MARKER of.
_OPTIONS_SYSTEM = """You are reading the answer OPTIONS of ONE exam question from
its OCR text. The option markers may be OCR-garbled (a stray ";ंद्ध" or ";क)"
instead of "(a)"/"(d)"), and two options may sit on one line separated by tabs.

Return ONLY a JSON array of the option TEXTS in a,b,c,d order, verbatim, marker
stripped, no prose:
["option a text","option b text","option c text","option d text"]

- Return exactly the options that are really there, in order. Almost always 4.
- Copy the option text EXACTLY as written — do not translate, correct, or invent.
- If an option is genuinely unreadable, put its best-effort text; do not drop it
  or the count will be wrong."""


def reread_options(region_text: str, n) -> list[str] | None:
    """Content-read escalation: return this one question's option strings, or None.
    Used only when a boundary is stable but the slicer produced the wrong option
    count (a garbled marker). Reads options only — never the stem."""
    user = f"Read the options of question {n} from this text:\n\n{region_text}"
    raw = complete(_OPTIONS_SYSTEM, user, model=_BOUNDARY_MODEL, max_tokens=1024)
    s = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    s = re.sub(r"\s*```\s*$", "", s).strip()
    try:
        data = parse_json(s)
    except (ValueError, json.JSONDecodeError):
        return None
    if isinstance(data, list) and all(isinstance(o, str) for o in data):
        return [o.strip() for o in data if o.strip()]
    return None
