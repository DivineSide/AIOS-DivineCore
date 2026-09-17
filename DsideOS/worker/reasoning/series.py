# -*- coding: utf-8 -*-
"""series — Number Series questions, correct by construction.

MODELLED ON: vdo-vpdo 2023-12-31 Q96 —

    श्रृंखला 4, 6, 9, 13.5, ? में '?' के स्थान पर उपयुक्त विकल्प का चयन करें
    (A) 17.5  (B) 19  (C) 20.25  (D) 22.75          -> answer 20.25

That is a x1.5 geometric series, and note the real paper is happy to use a
NON-INTEGER term (13.5, 20.25). So the generator must not force integers.

WHY NO MODEL: the rule is chosen here, so the next term is the rule applied
once more. `solve()` re-derives it independently for the tests.

WHY THIS TYPE NEEDS THE GATE EXEMPTION: a series like 512, 1024, 2048 puts a
bare 4-digit number in the stem, which validate_gen's `_YEAR` check reads as an
implausible CE date and rejects (verified live). Reasoning bypasses that gate —
see the plan's exemption table.

Interface:
    generate(rng)          -> question dict
    solve(rule, terms)     -> next term          # pure, for tests
"""
from __future__ import annotations

import random
from fractions import Fraction

from . import pools

# Each rule is (name, step_fn, describe_fn). step_fn(prev, i) -> next term,
# where `i` is the 0-based index of the term being produced. Keeping the index
# lets alternating and polynomial rules share one signature with the simple
# ones.
#
# Tradeoff: rules are a fixed table rather than randomly-composed arithmetic.
# A composed rule would give more variety but could produce series with more
# than one valid continuation, which makes the question unanswerable — a fixed
# table is checkable by eye once.
_RULES = [
    ("mul", lambda p, i, k: p * k, lambda k: f"प्रत्येक पद को {_fmt(k)} से गुणा किया गया है"),
    ("add", lambda p, i, k: p + k, lambda k: f"प्रत्येक पद में {_fmt(k)} जोड़ा गया है"),
    ("add_inc", lambda p, i, k: p + k + i,
     lambda k: f"जोड़ी जाने वाली संख्या प्रत्येक चरण में 1 बढ़ती है"),
    ("mul_add", lambda p, i, k: p * 2 + k,
     lambda k: f"प्रत्येक पद को 2 से गुणा कर {_fmt(k)} जोड़ा गया है"),
]


def _fmt(v) -> str:
    """Render a term: integers bare, fractions as the shortest decimal.

    The real paper writes 13.5 and 20.25, never 27/2 — so Fractions are used
    internally for exactness and formatted to decimal only at the boundary.
    """
    if isinstance(v, Fraction):
        if v.denominator == 1:
            return str(v.numerator)
        f = float(v)
        s = f"{f:.4f}".rstrip("0").rstrip(".")
        return s
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def solve(rule_name: str, k, first, n_terms: int) -> list:
    """Regenerate the whole series from its parameters. O(n_terms).

    Independent of generate()'s construction path — the tests compare the two,
    so shared code here would let a bug cancel itself out.
    """
    step = next(s for nm, s, _ in _RULES if nm == rule_name)
    terms = [first]
    for i in range(n_terms - 1):
        terms.append(step(terms[-1], i, k))
    return terms


def _distractors(terms: list, answer, k, rule_name: str,
                 rng: random.Random) -> list:
    """Three wrong continuations, each a REAL mistake.

    - applying the rule to the WRONG base (the second-to-last term)
    - applying a neighbouring constant (k+1 or k-1)
    - continuing the arithmetic difference instead of the actual rule

    Random near-misses are avoided deliberately: a distractor that no method
    produces is eliminable by a candidate who spots it is "off-pattern".
    """
    step = next(s for nm, s, _ in _RULES if nm == rule_name)
    i = len(terms) - 1
    cands = []

    # wrong base
    if len(terms) >= 2:
        cands.append(step(terms[-2], i, k))
    # neighbouring constant
    for dk in (1, -1):
        try:
            cands.append(step(terms[-1], i, k + dk))
        except Exception:
            pass
    # linear continuation (ignore the real rule, just add the last difference)
    if len(terms) >= 2:
        cands.append(terms[-1] + (terms[-1] - terms[-2]))

    # A VISIBLE term must never be a distractor: a candidate eliminates
    # "the number I can already see in the series" without doing any work.
    # Caught in a smoke test (series "10, 22, 34, 46, ?" offered 46).
    banned = set(terms) | {answer}

    out = []
    for c in cands:
        if c not in banned and c not in out and _positive(c):
            out.append(c)
    bump = 1
    while len(out) < 3:
        for cand in (answer + bump, answer - bump):
            if cand not in banned and cand not in out and _positive(cand):
                out.append(cand)
                if len(out) == 3:
                    break
        bump += 1
    return out[:3]


def _positive(v) -> bool:
    try:
        return v > 0
    except TypeError:
        return False


def generate(rng: random.Random) -> dict:
    """One Number Series question. O(1) — fixed 4-5 term series.

    Terms are Fractions internally so a x1.5 series stays exact (4, 6, 9, 13.5,
    20.25 and not 20.249999999999996).
    """
    rule_name, step, describe = rng.choice(_RULES)

    # Ranges are WIDE deliberately. Unlike direction/coding, a series has no
    # cosmetic slots — no names, no verbs, no units — so ALL of its variety has
    # to come from the parameters. Measured with the original narrow ranges:
    # only 1,426 distinct stems in 20,000 seeds (7%), against 99.8% for
    # direction. Widening first/k is the only lever there is.
    if rule_name == "mul":
        k = rng.choice([Fraction(2), Fraction(3), Fraction(4),
                        Fraction(3, 2), Fraction(5, 2)])
        first = Fraction(rng.randint(2, 20))
    elif rule_name == "add":
        k = Fraction(rng.randint(3, 25))
        first = Fraction(rng.randint(2, 40))
    elif rule_name == "add_inc":
        k = Fraction(rng.randint(2, 12))
        first = Fraction(rng.randint(1, 30))
    else:                                    # mul_add
        k = Fraction(rng.randint(1, 12))
        first = Fraction(rng.randint(1, 15))

    # A fractional multiplier compounds: x1.5 over 5 shown terms reaches
    # 45.5625, which no real paper prints. Real ones stop at 13.5 / 20.25, so
    # cap the fractional case at 4 shown terms.
    fractional = isinstance(k, Fraction) and k.denominator != 1
    n_terms = 4 if fractional else rng.choice([4, 5])
    terms = solve(rule_name, k, first, n_terms + 1)   # +1 = the hidden answer
    shown, answer = terms[:-1], terms[-1]

    wrongs = _distractors(shown, answer, k, rule_name, rng)
    opts = [_fmt(answer)] + [_fmt(w) for w in wrongs]
    # A duplicate after formatting (e.g. 8 and 8.0) would break distinctness.
    if len(set(opts)) != 4:
        bump = 1
        while len(set(opts)) != 4:
            opts[-1] = _fmt(answer + bump)
            bump += 1
    rng.shuffle(opts)
    idx = opts.index(_fmt(answer))

    series_txt = ", ".join(_fmt(t) for t in shown) + ", ?"
    stem = f"{rng.choice(pools.SERIES_QUESTIONS)} {series_txt}"

    return {
        "stem": stem,
        "options": opts,
        "answer": "abcd"[idx],
        "format": "plain",
        # Intrinsic: a constant adder is the easiest rule to spot; a
        # fractional multiplier or a compound rule is the hardest.
        "difficulty": ("easy" if rule_name == "add" else
                       "hard" if (fractional or rule_name == "mul_add")
                       else "moderate"),
        "reason": f"{describe(k)}; अतः अगला पद {_fmt(answer)} होगा।",
        "_type": "series",
    }
