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


def validate_question(q: dict) -> str | None:
    """None if valid, else a model-actionable reason."""
    stem = q.get("stem") or ""
    if len(stem.strip()) < 15:
        return "stem is missing or under 15 characters"
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


class PaperGuard:
    """Cross-question guards for one paper. Mutable; one instance per run."""

    def __init__(self):
        self._stems: set[str] = set()
        self._answer_texts: set[str] = set()

    def check(self, q: dict) -> str | None:
        stem_key = _norm(q.get("stem", ""))
        if stem_key in self._stems:
            return "duplicate question: this stem already exists in the paper"
        opts = q.get("options") or []
        ans = str(q.get("answer", "")).lower()
        idx = "abcd".find(ans)
        # entity-repeat: the same correct-answer TEXT appearing twice means the
        # paper asks about the same entity twice (नित्यानंद स्वामी ×3 bug).
        # Only meaningful for plain questions — कूट/statement option texts are
        # generic ("1 2 3 4", "केवल 1 और 2") and would false-positive.
        if q.get("format", "plain") == "plain" and 0 <= idx < len(opts):
            akey = _norm(opts[idx])
            if akey in self._answer_texts:
                return (f"the correct answer '{opts[idx]}' is already the answer of "
                        f"another question — ask about a DIFFERENT fact/entity")
        return None

    def commit(self, q: dict) -> None:
        self._stems.add(_norm(q.get("stem", "")))
        opts = q.get("options") or []
        idx = "abcd".find(str(q.get("answer", "")).lower())
        if q.get("format", "plain") == "plain" and 0 <= idx < len(opts):
            self._answer_texts.add(_norm(opts[idx]))
