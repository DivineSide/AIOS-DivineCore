# -*- coding: utf-8 -*-
"""util — the two routines every reasoning generator needs.

WHY THIS EXISTS: `distinct_wrongs` and `finish` were copy-pasted into every
generator (three near-identical `±bump` loops at direction.py, series.py and
coding.py; five copies of the shuffle-and-index idiom). Seven more types would
have made that ten copies of logic that must behave identically everywhere —
notably the "a distractor is never equal to the answer" invariant, which is a
correctness property, not a style one.

DESIGN RULE THIS ENCODES: a distractor must be a REAL MISTAKE — the value a
candidate lands on by stopping early, applying the rule to the wrong base, or
mis-remembering a step. `candidates` carries those, in preference order. The
`±bump` ladder is only a LAST RESORT for when the real mistakes collide or run
out; a question whose wrong options are all bumps is a weaker question, so
generators should pass as many genuine candidates as they can.

Interface:
    distinct_wrongs(answer, candidates, rng, n=3, banned=()) -> list
    finish(correct, wrongs, rng)                             -> (options, letter)
"""
from __future__ import annotations

import random
from typing import Any, Callable, Iterable, Sequence


def distinct_wrongs(answer: Any,
                    candidates: Iterable[Any],
                    rng: random.Random,
                    n: int = 3,
                    banned: Iterable[Any] = (),
                    bump: Callable[[Any, int], Any] | None = None,
                    ) -> list[Any]:
    """`n` distinct wrong answers, preferring genuine mistakes.

    `candidates` — values a candidate actually arrives at by a wrong method,
    in preference order. Duplicates, the answer itself, and anything in
    `banned` are filtered out.

    `banned` — values that must never be offered even though they are wrong.
    The real use is "already visible to the student": a number series must not
    offer a term it already printed (a candidate eliminates it without doing
    any arithmetic — a live bug, see series.py).

    `bump` — how to synthesise a fallback when `candidates` runs dry, as
    `bump(answer, i)` for i = 1, 2, 3... Defaults to numeric `answer ± i`,
    which only works when `answer` is a number; a type whose answers are words
    or times MUST pass its own, or it gets a short list back.

    Returns as many as it can, up to `n` — it never raises and never pads with
    the answer. A caller that needs exactly `n` should assert on the length;
    the test suite's structural check (4 distinct options) catches a shortfall
    for every registered type, so a silent partial return cannot ship.

    Complexity: O(len(candidates) + n * tries).
    """
    ban = set()
    for b in list(banned) + [answer]:
        try:
            ban.add(b)
        except TypeError:                    # unhashable — compare by equality
            pass

    out: list[Any] = []

    def _ok(v: Any) -> bool:
        if v == answer or v in out:
            return False
        try:
            if v in ban:
                return False
        except TypeError:
            pass
        return True

    for c in candidates:
        if len(out) >= n:
            break
        if _ok(c):
            out.append(c)

    if len(out) < n and bump is None and isinstance(answer, (int, float)):
        def bump(a, i):                      # noqa: E306 — local default
            return a + i if i % 2 else a - (i // 2 + i % 2)

    if bump is not None:
        i = 1
        while len(out) < n and i < 200:      # bounded: never spin
            for cand in (bump(answer, i), bump(answer, -i)):
                if cand is None:
                    continue
                positive = True
                if isinstance(cand, (int, float)):
                    positive = cand > 0      # a negative distance is not wrong, it is nonsense
                if positive and _ok(cand):
                    out.append(cand)
                    if len(out) >= n:
                        break
            i += 1

    return out[:n]


def finish(correct: str, wrongs: Sequence[str],
           rng: random.Random) -> tuple[list[str], str]:
    """Shuffle the four options and return (options, answer_letter).

    The idiom every generator ended with, in one place: put the correct option
    among the wrong ones, shuffle, then find where it landed. Returning the
    LETTER (not the index) matches the question-dict contract.

    Raises ValueError when the options are not 4 distinct non-empty strings —
    deliberately loud. A generator that produces a duplicate option has a bug
    in its distractor logic, and silently shipping three-option questions is
    worse than failing the run.
    """
    opts = [correct] + list(wrongs)
    if len(opts) != 4:
        raise ValueError(f"need exactly 4 options, got {len(opts)}: {opts!r}")
    if len({str(o) for o in opts}) != 4:
        raise ValueError(f"options must be distinct, got {opts!r}")
    if any(not str(o).strip() for o in opts):
        raise ValueError(f"options must be non-empty, got {opts!r}")

    opts = [str(o) for o in opts]
    rng.shuffle(opts)
    return opts, "abcd"[opts.index(str(correct))]
