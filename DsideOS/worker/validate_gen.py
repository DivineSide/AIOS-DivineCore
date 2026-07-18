# -*- coding: utf-8 -*-
"""validate_gen — mechanical invariant gate for GENERATED questions.

Same convention as the extraction harness's validate.py: every check is pure
code, every failure returns a SPECIFIC reason string (fed back to the model by
the informed-retry loop), None means the question passes.

Two levels:
  validate_question(q)          — per-question structure + content sanity
  PaperGuard().check(q)         — cross-question guards for one paper
                                  (stem dedup + entity-repeat)
"""
from __future__ import annotations

import math
import os
import re

_LETTERS = {"a", "b", "c", "d"}
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

# CE years must be plausible; the corpus damage taught us generated text can
# inherit impossible dates. ई०पू० (BCE) is exempt — 4000 ई.पू. is a real fact.
_YEAR = re.compile(r"\b([1-9][0-9]{3})\b(?!\s*ई[.०]?\s*पू)")
_YEAR_MIN, _YEAR_MAX = 600, 2026

# Shape classes for the eliminability check (client rule: options must be
# confusing, never eliminable by KIND). Code can't judge semantic confusability
# — the prompt owns that — but a 3-1 SHAPE split (one bare year among three
# names) is the objectively eliminable case, and shape is mechanical.
_SHAPE_YEAR = re.compile(r"^[0-9]{3,4}(\s*[-–]\s*[0-9]{2,4})?(\s*ई[.०]?(\s*पू[.०]?)?)?$")
_SHAPE_NUM = re.compile(r"^[0-9][0-9,.\s/%]*$")


def _shape_class(s: str) -> str:
    t = str(s).strip()
    if _SHAPE_YEAR.match(t):
        return "year"
    if _SHAPE_NUM.match(t):
        return "number"
    return "devanagari-text" if _dev_ratio(t) >= 0.5 else "latin-text"


def _odd_shape_out(items: list[str]) -> str | None:
    """The one item whose shape-class differs from the other three, or None."""
    classes = [_shape_class(i) for i in items]
    for cls in set(classes):
        if classes.count(cls) == 1 and len(items) == 4:
            return items[classes.index(cls)]
    return None


def _dev_ratio(text: str) -> float:
    letters = _LETTER.findall(text)
    if not letters:
        return 0.0
    return sum(1 for c in letters if _DEVANAGARI.match(c)) / len(letters)


def _norm(s: str) -> str:
    return " ".join(str(s).split()).lower()


# The student never sees the retrieval passages, so neither the stem nor the
# teacher-facing reason may cite them (prompt teaches this; this gate enforces
# it — informed retry rewrites offenders). Phrases only, not bare words:
# "स्रोत" alone is legal ("ऊर्जा के स्रोत"), citation phrasings are not.
_MATERIAL_REFS = (
    "पाठ के अनुसार", "सामग्री के अनुसार", "अध्ययन सामग्री", "प्रदत्त सामग्री",
    "दी गई सामग्री", "उपरोक्त सामग्री", "पाठ में", "स्रोत [",
    "के साथ उल्लेखित", "सामग्री में", "सामग्री से",
)


def validate_question(q: dict) -> str | None:
    """None if valid, else a model-actionable reason."""
    stem = q.get("stem") or ""
    if len(stem.strip()) < 15:
        return "stem is missing or under 15 characters"
    for ref in _MATERIAL_REFS:
        where = "stem" if ref in stem else (
            "reason" if ref in str(q.get("reason") or "") else None)
        if where:
            return (f"the {where} contains '{ref}' — the student never sees the "
                    f"study material, so never refer to it; ask a standalone "
                    f"question and state the reason as the bare fact")
    full_text = " ".join([stem] + [str(s) for s in (q.get("statements") or [])]
                         + [" ".join(map(str, r)) for r in (q.get("match") or [])])
    if _dev_ratio(full_text) < 0.5:
        return "question text must be Hindi (Devanagari-majority)"

    opts = q.get("options")
    if not isinstance(opts, list) or len(opts) != 4:
        return f"exactly 4 options required, got {len(opts) if isinstance(opts, list) else 'none'}"
    if any(not isinstance(o, str) or not o.strip() for o in opts):
        return "every option must be non-empty text"
    if len({_norm(o) for o in opts}) != 4:
        return "options must be 4 distinct values"

    ans = str(q.get("answer", "")).lower()
    if ans not in _LETTERS:
        return "answer must be one of a/b/c/d"

    fmt = q.get("format", "plain")
    if fmt == "plain":
        odd = _odd_shape_out(opts)
        if odd is not None:
            return (f"option '{odd}' is a different KIND from the other three — "
                    f"students eliminate it without knowledge; make all 4 options "
                    f"the same kind of thing")
    if fmt == "match":
        rows = q.get("match")
        if not isinstance(rows, list) or len(rows) != 4:
            return "match question needs exactly 4 सूची rows"
        rights = [str(r[1]).split(". ", 1)[-1] for r in rows
                  if isinstance(r, (list, tuple)) and len(r) == 2]
        if len(rights) == 4:
            odd = _odd_shape_out(rights)
            if odd is not None:
                return (f"सूची-II item '{odd}' is a different KIND from the other "
                        f"three (mixed categories are eliminable) — all 4 must be "
                        f"the same kind: all years, all places, all works, etc.")
    if fmt in ("statement", "assertion", "order"):
        stmts = q.get("statements")
        if not isinstance(stmts, list) or not stmts:
            return f"{fmt} question needs its statements list"

    # year sanity — check ALL text incl. options
    for m in _YEAR.finditer(full_text + " " + " ".join(opts)):
        y = int(m.group(1))
        if not (_YEAR_MIN <= y <= _YEAR_MAX):
            return (f"the year {y} is implausible for a CE date "
                    f"(valid {_YEAR_MIN}-{_YEAR_MAX}; use ई०पू० for BCE)")
    return None


# Numeric-answer budget (answer-VARIETY gate, 2026-07-14). MEASURED from the
# client's real answered PYQs (632 plain questions): text answers 88.3%,
# number 6.2%, year 3.3%, latin 2.2%. Generation drifts hard toward year/number
# answers (dates are the most quotable facts, so they pass grounding easiest —
# survivorship bias): the first Sarvam paper came out ~90% numeric, the inverse
# of the real exam. The cap gives 2x headroom over the measured ~10% share.
_NUMERIC_SHARE_CAP = float(os.environ.get("GEN_NUMERIC_CAP", "0.2"))
_NUMERIC_CLASSES = {"year", "number"}


class PaperGuard:
    """Cross-question guards for one paper. Mutable; one instance per run.

    `total` (expected paper size) sizes the numeric-answer budget; without it
    the budget is disabled (single-question/unknown-size callers)."""

    def __init__(self, total: int | None = None):
        self._stems: set[str] = set()
        self._answer_texts: set[str] = set()
        self._numeric_answers = 0
        self._numeric_cap = (max(1, math.ceil(total * _NUMERIC_SHARE_CAP))
                             if total else None)

    @staticmethod
    def _answer_text(q: dict) -> str | None:
        """Correct-option text for plain questions, else None (कूट/statement
        option texts are generic and would false-positive every guard)."""
        if q.get("format", "plain") != "plain":
            return None
        opts = q.get("options") or []
        idx = "abcd".find(str(q.get("answer", "")).lower())
        return opts[idx] if 0 <= idx < len(opts) else None

    def check(self, q: dict) -> str | None:
        stem_key = _norm(q.get("stem", ""))
        if stem_key in self._stems:
            return "duplicate question: this stem already exists in the paper"
        atext = self._answer_text(q)
        if atext is None:
            return None
        # entity-repeat: the same correct-answer TEXT appearing twice means the
        # paper asks about the same entity twice (नित्यानंद स्वामी ×3 bug).
        if _norm(atext) in self._answer_texts:
            return (f"the correct answer '{atext}' is already the answer of "
                    f"another question — ask about a DIFFERENT fact/entity")
        # numeric-answer budget: real papers are ~90% text-answered; a paper
        # full of साल/संख्या answers reads machine-made and tests only dates.
        if (self._numeric_cap is not None
                and _shape_class(atext) in _NUMERIC_CLASSES
                and self._numeric_answers >= self._numeric_cap):
            return (f"this paper already has {self._numeric_answers} questions "
                    f"whose answer is a year/number — real papers are ~90% "
                    f"text-answered. Ask WHO/WHICH/WHAT about this topic: a "
                    f"person, place, organisation, book, scheme or term")
        return None

    def commit(self, q: dict) -> None:
        self._stems.add(_norm(q.get("stem", "")))
        atext = self._answer_text(q)
        if atext is not None:
            self._answer_texts.add(_norm(atext))
            if _shape_class(atext) in _NUMERIC_CLASSES:
                self._numeric_answers += 1
