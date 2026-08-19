# -*- coding: utf-8 -*-
"""Pass 2 of the two-pass extractor: the DUMB pass. No AI, no tokens, no cost.

Pass 1 (extract_boundaries) already made the only decision that needs
intelligence — where each question's lines are. Pass 2 just takes those exact
source lines and mechanically splits stem from options. Because the text is
COPIED VERBATIM from the OCR source and never sent back through a model, nothing
here can introduce a spelling mistake or hallucinate a missing option. What OCR
read is what ships (spelling is fixed later by the guarded proofread stage).

The one non-trivial job here is reading OPTION MARKERS, and real papers make it
hard in a DETERMINISTIC (not fuzzy) way:
  * Two options per line, tab-separated:  "(a) केवल 1 \\t\\t\\t ;इ) 2 और 3"
  * The right-column marker is OCR-garbled: Sarvam maps "(b)"->";इ)" / ";ब)"
    and "(d)"->";क)" consistently (verified: ;क) appears ~103x, once per question,
    exactly like (a)/(c)). "(a)" and "(c)" (left column) stay clean.
These are fixed by a lookup table (`_MARKER_FIXES`), never by guessing — the
letter/position is unambiguous once the garble is mapped.
"""
from __future__ import annotations

import re

# Reuse the existing Kruti-Dev-era marker normalizer (handles the ¼a½ / A½
# legacy-font styles); we ADD the Sarvam-OCR garble fixes below.
from extract_docx import _normalize_option_markers


# Sarvam-OCR garbled option markers -> the clean label they represent. Verified
# against real papers BY COLUMN POSITION: on a 4-on-one-line row the visual order
# is "(a) ;इ) ;ब) ;क)" == a,b,c,d, and whole-paper counts confirm ;इ)==(b) (42x,
# same slot as the 61 clean "(b)"), ;ब)==(c) (rare), ;क)==(d) (~103x, once per Q).
# Only well-attested garbles go here; NOVEL one-off garbles (e.g. Q44's ";ंद्ध"
# for (a)) are deliberately left for the informed-retry loop rather than chasing
# every variant into this table (that is the carve-out rot we are avoiding).
_MARKER_FIXES = [
    (r";\s*इ\s*\)", "(b) "),
    (r";\s*ब\s*\)", "(c) "),
    (r";\s*क\s*\)", "(d) "),
    (r";\s*घ\s*\)", "(d) "),
]

# A clean option marker at a token boundary: (a) / (b) / (c) / (d), any case.
_MARKER = re.compile(r"\(\s*([a-dA-D])\s*\)\s*")

# The tab run the OCR uses to separate the two columns on one option line.
_COL_SEP = re.compile(r"\t+| {4,}")


def _fix_markers(text: str) -> str:
    """Normalize ALL option markers to clean '(a) (b) (c) (d)' — legacy Kruti-Dev
    styles (via the existing normalizer) AND the Sarvam-OCR right-column garble."""
    text = _normalize_option_markers(text)     # legacy ¼a½ / A½ styles
    for pat, rep in _MARKER_FIXES:
        text = re.sub(pat, rep, text)
    return text


def _split_options(region: str) -> tuple[str, list[str]]:
    """Given a question's full text region (markers already fixed), split it into
    (stem, options) purely by marker position. The stem is everything before the
    first '(a)'; options are the marker-delimited spans after it, in a/b/c/d
    order. Two-column tab-separated option rows are handled by the marker scan
    (both markers on a line are found in order)."""
    # Flatten the column separator so "(a) X \t\t (b) Y" reads as "(a) X  (b) Y".
    flat = _COL_SEP.sub("  ", region)

    markers = list(_MARKER.finditer(flat))
    if not markers:
        return region.strip(), []

    stem = flat[: markers[0].start()].strip()

    options: list[str] = []
    for i, m in enumerate(markers):
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(flat)
        opt = flat[start:end].strip()
        options.append((m.group(1).lower(), opt))

    # keep options in a,b,c,d order; dedupe a marker that appears twice (keep first)
    seen = set()
    ordered = []
    for label in "abcd":
        for lab, opt in options:
            if lab == label and lab not in seen and opt:
                ordered.append(opt)
                seen.add(lab)
                break
    # if markers weren't a/b/c/d (rare), fall back to marker order
    if not ordered:
        ordered = [opt for _, opt in options if opt]

    return stem, ordered


def slice_question(raw_lines: list[str], start_line: int, end_line: int,
                   n: int | None = None) -> dict:
    """Turn ONE boundary (1-based inclusive line range) into a question dict.

    raw_lines[i] is line i+1 (as produced by extract_boundaries.number_lines), so
    the model's line numbers index straight in. Pure slicing — the text is the
    OCR source verbatim, only the option MARKERS are normalized.
    """
    # clamp to the available lines (defensive against an out-of-range boundary)
    lo = max(1, start_line)
    hi = min(len(raw_lines), end_line)
    region = "\n".join(raw_lines[lo - 1: hi])
    region = _fix_markers(region)
    stem, options = _split_options(region)
    return {"n": n, "stem": stem, "options": options}


def slice_all(raw_lines: list[str], boundaries: list[dict]) -> list[dict]:
    """Slice every boundary into a question dict, preserving order and numbering."""
    out = []
    for i, b in enumerate(boundaries, 1):
        q = slice_question(raw_lines, b["start_line"], b["end_line"],
                           n=b.get("n") or i)
        # carry the model's confidence through so the loop can act on it
        q["_confidence"] = b.get("confidence", "high")
        out.append(q)
    return out
