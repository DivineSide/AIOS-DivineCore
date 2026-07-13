# -*- coding: utf-8 -*-
"""formats — per-format generation contracts where the MODEL supplies knowledge
and CODE builds the structure.

The old pipeline asked the model for finished questions and hoped the कूट grid
was internally consistent. Here, for every non-plain format the model returns
only the FACTS (pairs, statements, the correct order, the A/R relation) and
this module deterministically assembles the stem block, the option set, and —
critically — the answer letter. A structurally inconsistent सुमेलित question
(कूट options that don't contain the real mapping, an answer letter pointing at
the wrong permutation) is thereby impossible, not merely discouraged.

Each format defines:
  PROMPT   — what the model must return (JSON, knowledge only)
  build()  — dict from the model -> a Question dict in the paper builder's
             existing structured schema (build_paper.py renders `statements`,
             `match`, `lead_in`, `long_options` natively)
Every build() raises FormatError with a SPECIFIC reason on bad input — that
reason is fed back to the model by the retry loop (informed correction).

Answer positions are shuffled with a per-slot seeded RNG so correct answers
spread across (a)-(d) without run-to-run nondeterminism inside one paper.
"""
from __future__ import annotations

import random

_LETTERS = ["a", "b", "c", "d"]


class FormatError(ValueError):
    """Raised with a model-actionable reason when a draft can't be assembled."""


def _need(draft: dict, key: str, typ=None):
    if key not in draft:
        raise FormatError(f"missing required field '{key}'")
    v = draft[key]
    if typ is not None and not isinstance(v, typ):
        raise FormatError(f"field '{key}' must be {typ.__name__}")
    return v


def _clean_str(v, field: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise FormatError(f"field '{field}' must be a non-empty string")
    return " ".join(v.split())


# ── plain ────────────────────────────────────────────────────────────────────

PLAIN_PROMPT = """{{
  "stem": "<question text in Hindi>",
  "options": ["<a>", "<b>", "<c>", "<d>"],
  "answer_index": <0-3, index of the CORRECT option in your list>,
  "reason": "<=160 chars: why the correct option is right>"
}}
DISTRACTORS (client rule): all 4 options must be the same KIND of thing and
genuinely confusable — a wrong year NEAR the right one, a sibling ruler, a
neighbouring place. Never one odd-shaped option (one date among three names)
that students can eliminate without knowledge."""


def build_plain(draft: dict, rng: random.Random) -> dict:
    stem = _clean_str(_need(draft, "stem"), "stem")
    options = _need(draft, "options", list)
    if len(options) != 4:
        raise FormatError(f"exactly 4 options required, got {len(options)}")
    options = [_clean_str(o, "options[]") for o in options]
    idx = _need(draft, "answer_index")
    if not isinstance(idx, int) or not 0 <= idx <= 3:
        raise FormatError("answer_index must be an integer 0-3")
    correct = options[idx]
    rng.shuffle(options)
    return {
        "stem": stem,
        "options": options,
        "answer": _LETTERS[options.index(correct)],
        "reason": str(draft.get("reason", "")).strip()[:200],
        "format": "plain",
    }


# ── match (सुमेलित) ──────────────────────────────────────────────────────────

MATCH_PROMPT = """{{
  "stem_subject": "<what is being matched, e.g. 'लेखक और उनकी रचनाएँ'>",
  "pairs": [["<सूची-I item>", "<its CORRECT सूची-II match>"], ...exactly 4],
  "reason": "<=160 chars: source basis of the pairing>"
}}
The pairs you give ARE the correct answer — do not scramble them.
HOMOGENEITY (client rule): all 4 सूची-I items must be the same KIND of thing,
and all 4 सूची-II items must be the same KIND of thing (all years, or all
places, or all works, or all persons...). A mixed list (one date among three
names) lets students eliminate by category without knowing the subject —
rejected."""

_MATCH_LEFT_LABELS = ["a", "b", "c", "d"]
_LEAD_IN = "निम्नलिखित विकल्पों में से सही उत्तर चुनिए :"


def _permutations_pool(rng: random.Random) -> list[tuple[int, ...]]:
    """All 4-item permutations except identity, shuffled."""
    import itertools
    pool = [p for p in itertools.permutations(range(4)) if p != (0, 1, 2, 3)]
    rng.shuffle(pool)
    return pool


def build_match(draft: dict, rng: random.Random) -> dict:
    pairs = _need(draft, "pairs", list)
    if len(pairs) != 4:
        raise FormatError(f"exactly 4 pairs required, got {len(pairs)}")
    lefts, rights = [], []
    for i, p in enumerate(pairs):
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise FormatError(f"pairs[{i}] must be a [left, right] pair")
        lefts.append(_clean_str(p[0], f"pairs[{i}][0]"))
        rights.append(_clean_str(p[1], f"pairs[{i}][1]"))
    if len(set(lefts)) != 4 or len(set(rights)) != 4:
        raise FormatError("सूची items must be 4 distinct entries on each side")

    # सूची-II is displayed in a scrambled order; the correct कूट maps a-d to
    # the displayed numbers. Code owns ALL of this — the model only gave pairs.
    display = list(range(4))
    rng.shuffle(display)                       # display[j] = pair index shown as item j+1
    correct_code = tuple(display.index(i) for i in range(4))  # a-d -> displayed number-1

    # 3 distractor codes: other permutations, none equal to the correct one.
    distractors = [p for p in _permutations_pool(rng) if p != correct_code][:3]
    codes = distractors + [correct_code]
    rng.shuffle(codes)
    answer = _LETTERS[codes.index(correct_code)]

    def fmt_code(code: tuple[int, ...]) -> str:
        return "  ".join(str(n + 1) for n in code)

    subject = _clean_str(draft.get("stem_subject", "निम्नलिखित"), "stem_subject")
    stem = (f"{subject} के संदर्भ में सूची-I को सूची-II से सुमेलित कीजिए तथा "
            f"नीचे दिए गए कूट की सहायता से सही उत्तर चुनिए :")
    # row i: left column shows lefts in a-d order; right column shows the
    # SCRAMBLED rights numbered 1-4 (display[i] = which pair's right sits at row i)
    match_rows = [[f"{_MATCH_LEFT_LABELS[i]}. {lefts[i]}",
                   f"{i + 1}. {rights[display[i]]}"]
                  for i in range(4)]
    return {
        "stem": stem,
        "match": match_rows,
        "lead_in": "कूट :  (a b c d के लिए क्रमशः)",
        "options": [fmt_code(c) for c in codes],
        "answer": answer,
        "long_options": False,
        "reason": str(draft.get("reason", "")).strip()[:200],
        "format": "match",
        # provenance for the grounding gate: the actual pairing claim
        "_claim": "; ".join(f"{l} → {r}" for l, r in zip(lefts, rights)),
    }


# ── statement (कथन-आधारित) ───────────────────────────────────────────────────

STATEMENT_PROMPT = """{{
  "context": "<topic line, e.g. 'उत्तराखंड की जलविद्युत परियोजनाओं के संदर्भ में'>",
  "statements": ["<कथन 1>", "<कथन 2>", ...2 to 3 statements],
  "correct_indexes": [<0-based indexes of the TRUE statements>],
  "reason": "<=160 chars: why the true ones are true / false one is false>"
}}
At least one statement must be true and at least one false."""


def _statement_options(n: int, correct: frozenset[int]) -> tuple[list[str], int]:
    """Canonical option set for n statements; returns (options, correct_idx)."""
    def label(sel: frozenset[int]) -> str:
        if len(sel) == n:
            return "उपर्युक्त सभी"
        nums = " और ".join(str(i + 1) for i in sorted(sel))
        return f"केवल {nums}"
    # candidate selections: each single, common pairs, all — ensure correct present
    cands: list[frozenset[int]] = [frozenset([i]) for i in range(n)]
    if n >= 2:
        cands += [frozenset(c) for c in [(0, 1), (0, 2), (1, 2)] if max(c) < n]
    cands.append(frozenset(range(n)))
    seen, uniq = set(), []
    for c in [correct] + cands:
        if c not in seen and c:
            seen.add(c)
            uniq.append(c)
    sel4 = uniq[:4]
    if len(sel4) < 4:
        raise FormatError("could not build 4 distinct statement options")
    opts = [label(s) for s in sel4]
    return opts, sel4.index(correct)


def build_statement(draft: dict, rng: random.Random) -> dict:
    stmts = _need(draft, "statements", list)
    if not 2 <= len(stmts) <= 3:
        raise FormatError(f"2-3 statements required, got {len(stmts)}")
    stmts = [_clean_str(s, "statements[]") for s in stmts]
    idxs = _need(draft, "correct_indexes", list)
    correct = frozenset(i for i in idxs if isinstance(i, int) and 0 <= i < len(stmts))
    if not correct or len(correct) == len(stmts):
        raise FormatError("need at least one TRUE and at least one FALSE statement")

    options, correct_pos = _statement_options(len(stmts), correct)
    # shuffle while tracking the correct option
    correct_text = options[correct_pos]
    rng.shuffle(options)
    context = _clean_str(draft.get("context", "निम्नलिखित के संदर्भ में"), "context")
    return {
        "stem": f"{context} निम्नलिखित कथनों पर विचार कीजिए :",
        "statements": stmts,
        "lead_in": "उपर्युक्त कथनों में से कौन-सा/से सही है/हैं?",
        "options": options,
        "answer": _LETTERS[options.index(correct_text)],
        "reason": str(draft.get("reason", "")).strip()[:200],
        "format": "statement",
    }


# ── assertion (अभिकथन-कारण) ──────────────────────────────────────────────────

ASSERTION_PROMPT = """{{
  "assertion": "<कथन (A): a TRUE or FALSE factual claim>",
  "reason": "<कारण (R): a TRUE or FALSE explanatory claim>",
  "relation": "<one of: both-true-explains | both-true-not-explains | a-true-r-false | a-false-r-true>",
  "why": "<=160 chars: source basis>"
}}"""

_AR_OPTIONS = [
    "(A) और (R) दोनों सही हैं तथा (R), (A) की सही व्याख्या है",
    "(A) और (R) दोनों सही हैं, परन्तु (R), (A) की सही व्याख्या नहीं है",
    "(A) सही है, परन्तु (R) गलत है",
    "(A) गलत है, परन्तु (R) सही है",
]
_AR_ANSWER = {
    "both-true-explains": 0,
    "both-true-not-explains": 1,
    "a-true-r-false": 2,
    "a-false-r-true": 3,
}


def build_assertion(draft: dict, rng: random.Random) -> dict:
    assertion = _clean_str(_need(draft, "assertion"), "assertion")
    reason_txt = _clean_str(_need(draft, "reason"), "reason")
    rel = str(_need(draft, "relation")).strip()
    if rel not in _AR_ANSWER:
        raise FormatError(f"relation must be one of {sorted(_AR_ANSWER)}")
    # A/R options are canonical and NEVER shuffled (fixed convention in exams).
    return {
        "stem": ("नीचे दो वक्तव्य दिए गए हैं — एक को अभिकथन (A) तथा दूसरे को "
                 "कारण (R) कहा गया है :"),
        "statements": [f"अभिकथन (A) : {assertion}", f"कारण (R) : {reason_txt}"],
        "lead_in": "नीचे दिए गए कूट की सहायता से सही उत्तर चुनिए :",
        "options": list(_AR_OPTIONS),
        "answer": _LETTERS[_AR_ANSWER[rel]],
        "long_options": True,
        "reason": str(draft.get("why", "")).strip()[:200],
        "format": "assertion",
    }


# ── order (क्रम) ─────────────────────────────────────────────────────────────

ORDER_PROMPT = """{{
  "stem": "<what to order, e.g. 'निम्नलिखित को कालक्रमानुसार व्यवस्थित कीजिए'>",
  "items": ["<item 1>", ...exactly 4, ALREADY IN THE CORRECT ORDER],
  "reason": "<=160 chars: the dates/basis of the ordering>"
}}"""


def build_order(draft: dict, rng: random.Random) -> dict:
    items = _need(draft, "items", list)
    if len(items) != 4:
        raise FormatError(f"exactly 4 items required, got {len(items)}")
    items = [_clean_str(i, "items[]") for i in items]
    if len(set(items)) != 4:
        raise FormatError("items must be distinct")

    display = list(range(4))
    rng.shuffle(display)                     # numbered listing shown to the student
    correct_code = tuple(display.index(i) for i in range(4))
    distractors = [p for p in _permutations_pool(rng) if p != correct_code][:3]
    codes = distractors + [correct_code]
    rng.shuffle(codes)

    def fmt_code(code):
        return ", ".join(str(n + 1) for n in code)

    return {
        "stem": _clean_str(_need(draft, "stem"), "stem"),
        "statements": [f"{j + 1}. {items[display[j]]}" for j in range(4)],
        "lead_in": "नीचे दिए गए कूट की सहायता से सही क्रम चुनिए :",
        "options": [fmt_code(c) for c in codes],
        "answer": _LETTERS[codes.index(correct_code)],
        "reason": str(draft.get("reason", "")).strip()[:200],
        "format": "order",
        "_claim": " → ".join(items),
    }


# ── registry ─────────────────────────────────────────────────────────────────

FORMATS: dict[str, dict] = {
    "plain":     {"prompt": PLAIN_PROMPT,     "build": build_plain,
                  "label": "सीधा एक-तथ्य प्रश्न"},
    "match":     {"prompt": MATCH_PROMPT,     "build": build_match,
                  "label": "सुमेलित कीजिए (सूची-I/सूची-II)"},
    "statement": {"prompt": STATEMENT_PROMPT, "build": build_statement,
                  "label": "कथन-आधारित प्रश्न"},
    "assertion": {"prompt": ASSERTION_PROMPT, "build": build_assertion,
                  "label": "अभिकथन-कारण (A/R)"},
    "order":     {"prompt": ORDER_PROMPT,     "build": build_order,
                  "label": "सही क्रम"},
}


def build(fmt: str, draft: dict, seed: int) -> dict:
    """Assemble a Question dict from a model draft. Raises FormatError with a
    model-actionable reason on any structural problem."""
    if fmt not in FORMATS:
        raise FormatError(f"unknown format {fmt!r}")
    if not isinstance(draft, dict):
        raise FormatError("draft must be a JSON object")
    rng = random.Random(seed)
    return FORMATS[fmt]["build"](draft, rng)
