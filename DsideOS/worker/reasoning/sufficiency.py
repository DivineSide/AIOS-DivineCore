# -*- coding: utf-8 -*-
"""sufficiency — data-sufficiency questions, correct by construction.

MODELLED ON: police-constable 2025 ~Q31 — statements i/ii/iii about a value,
asked "which of these are sufficient to determine it?".

WHY THIS IS THE HARDEST TYPE HERE: every other generator computes a VALUE. This
one computes a PROPERTY OF THE CLUE SET — whether a subset pins the answer — so
the solver has to reason over subsets rather than evaluate an expression. The
question is not "what is x" but "could you know x from these".

HOW IT STAYS CORRECT: the underlying fact is chosen first (a person's age, a
number), then statements are generated as CONSTRAINTS over a small integer
domain. Sufficiency is then decided by BRUTE FORCE — enumerate every candidate
value in the domain, keep those satisfying the subset, and the subset is
sufficient iff exactly one survives. No cleverness, no heuristic: the same
definition the candidate applies, applied exhaustively.

That brute force is why the domain is deliberately small (ages 1-99). At that
size every subset check is ~100 predicate evaluations, which is nothing; a wider
domain would need real constraint solving and buy nothing pedagogically.

Interface:
    generate(rng)                       -> question dict
    satisfying(domain, constraints)     -> list[int]    # pure, for tests
    is_sufficient(domain, constraints)  -> bool         # pure, for tests
"""
from __future__ import annotations

import random
from typing import Callable

from . import pools
from .util import finish

# The four standard options. ORDER IS FIXED and they are never shuffled — real
# papers always print them in this order, and a candidate reads them as a
# scale (I alone / II alone / both / neither) rather than as four independent
# choices. `finish` is therefore NOT used here.
_OPTIONS = [
    "केवल कथन I पर्याप्त है",
    "केवल कथन II पर्याप्त है",
    "दोनों कथन मिलकर पर्याप्त हैं",
    "दोनों कथन मिलकर भी पर्याप्त नहीं हैं",
]

_DOMAIN = range(1, 100)

_STEMS = [
    "{name} की आयु क्या है ? नीचे दिए गए कथनों पर विचार कीजिए और बताइए कि "
    "उत्तर ज्ञात करने हेतु कौन-सा/से कथन पर्याप्त है/हैं ।",
    "{name} की आयु ज्ञात करनी है । निम्नलिखित कथनों में से कौन-सा/से इसके लिए "
    "पर्याप्त है/हैं ?",
]


def satisfying(domain, constraints: list[Callable[[int], bool]]) -> list[int]:
    """Values in `domain` satisfying every constraint. O(|domain| * |cons|)."""
    return [v for v in domain if all(c(v) for c in constraints)]


def is_sufficient(domain, constraints: list[Callable[[int], bool]]) -> bool:
    """True when the constraints pin exactly one value.

    THE definition of sufficiency, applied exhaustively. Independent of
    generate()'s construction path, for the tests.
    """
    return len(satisfying(domain, constraints)) == 1


def _make_clue(age: int, rng: random.Random,
               allow_exact: bool = False) -> tuple[str, Callable[[int], bool]]:
    """One true-but-partial statement about `age`, as (text, predicate).

    Every clue is TRUE of the real age by construction — the question is never
    about contradictory data, only about whether the true data is enough.

    `allow_exact` gates the clue that states the age outright. It is OFF by
    default because such a statement makes the question trivial: the candidate
    reads the answer instead of reasoning about sufficiency. Measured 1,852 of
    3,000 questions containing one before this gate existed. It is still
    reachable for the deliberate "statement I alone is sufficient" case, where
    ONE such clue is the whole point — but never for both statements.
    """
    kinds = ["range", "multiple", "parity_range", "square"]
    if allow_exact:
        kinds.append("exact")
    kind = rng.choice(kinds)

    if kind == "exact":
        return (f"{age} वर्ष है", lambda v, a=age: v == a)

    if kind == "range":
        lo = max(1, age - rng.randint(3, 10))
        hi = age + rng.randint(3, 10)
        return (f"{lo} और {hi} वर्ष के बीच है",
                lambda v, lo=lo, hi=hi: lo <= v <= hi)

    if kind == "multiple":
        divs = [d for d in (3, 4, 5, 6, 7) if age % d == 0]
        if not divs:                         # no divisor — fall back to a range
            lo, hi = max(1, age - 7), age + 7
            return (f"{lo} और {hi} वर्ष के बीच है",
                    lambda v, lo=lo, hi=hi: lo <= v <= hi)
        d = rng.choice(divs)
        return (f"{d} का गुणज है", lambda v, d=d: v % d == 0)

    if kind == "square":
        root = int(age ** 0.5)
        if root * root == age:
            return ("एक पूर्ण वर्ग संख्या है",
                    lambda v: int(v ** 0.5) ** 2 == v)
        lo, hi = max(1, age - 6), age + 6    # not a square — fall back
        return (f"{lo} और {hi} वर्ष के बीच है",
                lambda v, lo=lo, hi=hi: lo <= v <= hi)

    # parity + range
    lo = max(1, age - rng.randint(4, 12))
    hi = age + rng.randint(4, 12)
    even = age % 2 == 0
    word = "सम" if even else "विषम"
    return (f"{lo} और {hi} के बीच एक {word} संख्या है",
            lambda v, lo=lo, hi=hi, e=even: lo <= v <= hi and (v % 2 == 0) == e)


def generate(rng: random.Random) -> dict:
    """One data-sufficiency question. O(|domain|) per subset check.

    Aims for a spread across all four answers rather than always producing the
    "both together" case, which is what a naive generator converges on.
    """
    want = rng.choice([0, 1, 2, 2, 3])        # target answer index
    age = rng.randint(12, 75)

    for _ in range(120):
        # At most ONE statement may state the age outright, and only when the
        # intended answer is "that statement alone is sufficient".
        t1, c1 = _make_clue(age, rng, allow_exact=(want == 0))
        t2, c2 = _make_clue(age, rng, allow_exact=(want == 1))
        if t1 == t2:
            continue

        s1 = is_sufficient(_DOMAIN, [c1])
        s2 = is_sufficient(_DOMAIN, [c2])
        both = is_sufficient(_DOMAIN, [c1, c2])

        if s1 and not s2:
            got = 0
        elif s2 and not s1:
            got = 1
        elif not s1 and not s2 and both:
            got = 2
        elif not s1 and not s2 and not both:
            got = 3
        else:
            continue                          # both alone sufficient — no option
        if got != want:
            continue
        break
    else:                                     # pragma: no cover
        t1, c1 = (f"{age} वर्ष है", lambda v, a=age: v == a)
        t2, c2 = ("10 का गुणज है", lambda v: v % 10 == 0)
        got = 0

    name = rng.choice(pools.MALE_NAMES + pools.FEMALE_NAMES)
    stem = (rng.choice(_STEMS).format(name=name)
            + f"\nकथन I : {name} की आयु {t1} ।"
            + f"\nकथन II : {name} की आयु {t2} ।")

    n1 = len(satisfying(_DOMAIN, [c1]))
    n2 = len(satisfying(_DOMAIN, [c2]))
    nb = len(satisfying(_DOMAIN, [c1, c2]))

    return {
        "stem": stem,
        # NOT shuffled — see _OPTIONS. The answer letter is the option's fixed
        # position, which is what makes this type readable.
        "options": list(_OPTIONS),
        "answer": "abcd"[got],
        "format": "plain",
        # Intrinsic: "one statement alone does it" is visible at a glance;
        # deciding that BOTH together still fail is the hardest verdict.
        "difficulty": ("easy" if got in (0, 1) else
                       "moderate" if got == 2 else "hard"),
        "reason": (f"कथन I से {n1} संभावित मान बचते हैं, कथन II से {n2}, "
                   f"दोनों मिलकर {nb}; अतः {_OPTIONS[got]} ।"),
        "_type": "sufficiency",
        "_dedup_key": f"sufficiency:{t1}|{t2}",
    }
