# -*- coding: utf-8 -*-
"""The mechanical invariant gate for extracted questions.

The extraction harness has exactly one job: every question it emits must have a
real stem and exactly 4 real options. That invariant was previously expressed
only as prompt prose ("options: 2-6 strings") — which *permits* the failure it
should prevent: a truncated 2-option question is a "valid" response nothing
rejects. Real bug this catches: SET-02 Q118 shipped with 2 options, unflagged.

This module makes the invariant CODE, not a suggestion. `validate_question()` is
pure, deterministic, LLM-free — it returns None if a question is clean, or a
short machine-usable reason string if it is not. The two-pass extractor
(extract_two_pass) runs this after slicing and feeds any failure reason BACK to
the boundary model as informed-retry context.

It is the single owned home for "is this question usable?" rules (principle:
one mechanically-checkable rule list, not carve-outs scattered across a 53KB
file). Rules that already existed in extract_docx are reused here by import,
never re-implemented — see _REUSED below.
"""
from __future__ import annotations

# Reuse the existing, battle-tested validity helpers rather than re-implement
# them. These carry real bug-fix history (label-echo detection, cover-page
# detection, Kruti-Dev gibberish detection) and must stay the single source of
# truth. validate.py only ADDS the missing option-COUNT invariant on top.
from extract_docx import (          # noqa: E402  (sibling module, added to sys.path by caller)
    _all_options_placeholder,
    _looks_like_cover,
    _is_placeholder_option,
)

# The invariant. UKSSSC/UKPSC MCQs are 4-option. This is the check whose absence
# let Q118 (2 options) ship. Kept as a constant so a future 5-option exam is a
# one-line change, not a hunt through conditionals.
EXPECTED_OPTIONS = 4

# A stem shorter than this can't be a real question — it's a fragment the boundary
# pass mis-cut, or OCR noise. (A genuine MCQ stem is a full sentence.)
_MIN_STEM_LEN = 8

# The label letters an OCR captures INSTEAD of a real option (a/b/c/d markers).
# Deliberately NARROW: it must NOT include digits (maths options 8/24/40 are real)
# nor arbitrary single Devanagari letters (phonetics answers ब/फ/व/म are real).
# Only the conventional option-marker letters in both scripts.
_LABEL_LETTERS = set("abcdABCD") | set("अआइईउऊएऐओऔ") | set("कखगघ")


def _is_label_letter(opt) -> bool:
    """True only if the option, stripped of marker punctuation, is exactly ONE of
    the conventional label letters (a/b/c/d / अ/ब/स/द / क/ख/ग/घ). A digit or any
    other single char is NOT a label — it's a real (maths/grammar) answer."""
    if not isinstance(opt, str):
        return False
    core = opt.strip().strip("().[]। :-").strip()
    return len(core) == 1 and core in _LABEL_LETTERS


def validate_question(q: dict) -> str | None:
    """Return None if the question satisfies every invariant, else a SHORT reason
    string (machine- and model-readable) explaining the first failure.

    Pure code, no LLM. The reason string is fed back to the boundary model as
    informed-retry context, so keep it specific and actionable
    (e.g. "got 2 options, expected 4" not "invalid").
    """
    stem = q.get("stem")
    if not isinstance(stem, str) or len(stem.strip()) < _MIN_STEM_LEN:
        return f"stem too short or missing (len {len(stem.strip()) if isinstance(stem, str) else 0})"

    if _looks_like_cover(stem):
        return "stem looks like a cover-page / image description, not a question"

    opts = q.get("options")
    if not isinstance(opts, list):
        return "options is not a list"

    n = len(opts)
    if n != EXPECTED_OPTIONS:
        # THE Q118 check — the invariant that was missing.
        return f"got {n} option(s), expected {EXPECTED_OPTIONS}"

    if any(not isinstance(o, str) or not o.strip() for o in opts):
        return "an option is empty or non-string"

    # options that are only label letters (अ/ब/स/द, a/b/c/d) are not real choices
    if _all_options_placeholder(opts):
        return "options are only label placeholders (अ/ब/स/द), not real choices"

    # A lone bare-LABEL option (अ/ब/स/द, a/b/c/d) mixed among real ones means one
    # choice was lost to its marker. But a single-char NUMBER (8, 24's "8"...) or a
    # single Devanagari letter that is a genuine phonetics answer (ब/फ/व/म) is REAL
    # — maths and grammar questions legitimately have 1-char options. So only fire
    # on options that are specifically LABEL LETTERS, never digits or real answers.
    label_only = [i for i, o in enumerate(opts) if _is_label_letter(o)]
    if 0 < len(label_only) < n:              # some real, some label = a lost choice
        return f"option {label_only[0] + 1} is a bare label letter, not real text"

    # distinct options — two identical options means one was duplicated over a
    # real (unread) one
    norm = [o.strip() for o in opts]
    if len(set(norm)) < n:
        return "duplicate options (one choice likely lost)"

    return None


def is_valid(q: dict) -> bool:
    """Boolean convenience wrapper."""
    return validate_question(q) is None
