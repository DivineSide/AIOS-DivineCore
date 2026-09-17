# -*- coding: utf-8 -*-
"""grouping — logical set-membership questions, correct by construction.

MODELLED ON: vdo-vpdo 2023-12-31 Q99 —

    यदि i. कैलाश, गोविन्द और हरिन्दर बुद्धिमान हैं ।
        ii. कैलाश, राजेश और जितेन्द्र कठिन परिश्रमी हैं ।
        iii. राजेश, हरिन्दर और जितेन्द्र ईमानदार हैं ।
        iv. कैलाश, गोविन्द और जितेन्द्र महत्वाकांक्षी हैं ।
    तो कौन न तो ईमानदार है और न ही कठिन परिश्रमी है, किन्तु महत्वाकांक्षी है ?
                                                    -> answer गोविन्द

VERIFIED before building: exactly one person (गोविन्द) satisfies
`ambitious AND NOT honest AND NOT hardworking`. 5 people, 4 properties, 3 people
per property.

THE FAILURE MODE THIS TYPE HAS: a query that matches zero people (no answer) or
two (no single answer). Both ship silently unless checked. `_matches` is run
over every person before the question is emitted and the count must be exactly
1 — the same discipline arrangement.py needed, and for the same reason: an
unanswerable question is structurally perfect and semantically broken, so no
runtime gate catches it.

Interface:
    generate(rng)                 -> question dict
    matches(person, query, sets)  -> bool     # pure, for tests
"""
from __future__ import annotations

import random

from . import pools
from .util import distinct_wrongs, finish

# Properties, as (adjective, plural-verb phrase). Adjectives only — a property
# that is a noun ("डॉक्टर") would need a different verb and pluralisation.
_PROPERTIES = [
    ("बुद्धिमान", "बुद्धिमान हैं"),
    ("कठिन परिश्रमी", "कठिन परिश्रमी हैं"),
    ("ईमानदार", "ईमानदार हैं"),
    ("महत्वाकांक्षी", "महत्वाकांक्षी हैं"),
    ("अनुशासित", "अनुशासित हैं"),
    ("मिलनसार", "मिलनसार हैं"),
]

_ROMAN = ["i", "ii", "iii", "iv", "v"]


def matches(person: str, query: list[tuple[str, bool]],
            sets: dict[str, set[str]]) -> bool:
    """Does this person satisfy the query? O(len(query)).

    `query` is [(property, wanted), ...] — `wanted=False` means "NOT this".
    Independent of generate()'s construction, for the tests.
    """
    return all((person in sets[prop]) == wanted for prop, wanted in query)


def _render_query(query: list[tuple[str, bool]]) -> str:
    """The question clause, in the source paper's own phrasing.

    Negations first, then positives — "न तो X है और न ही Y है, किन्तु Z है"
    is how the real question reads, and putting the positives first makes the
    Hindi clumsy.
    """
    neg = [p for p, want in query if not want]
    pos = [p for p, want in query if want]
    parts = []
    if len(neg) == 2:
        parts.append(f"न तो {neg[0]} है और न ही {neg[1]}")
    elif len(neg) == 1:
        parts.append(f"{neg[0]} नहीं है")
    if pos:
        joined = " और ".join(pos)
        parts.append(f"{'किन्तु' if neg else ''} {joined} है".strip())
    return "तो निम्नलिखित में से कौन " + ", ".join(parts) + " ?"


def generate(rng: random.Random) -> dict:
    """One logical-grouping question. O(people * properties) per attempt.

    Builds the membership sets first, then searches for a query with EXACTLY
    one satisfying person. Rejects and resamples otherwise — a query matching
    zero or two people has no single right answer.
    """
    for _ in range(60):
        n_people = rng.choice([5, 5, 6])
        people = rng.sample(pools.MALE_NAMES, n_people)
        props = rng.sample(_PROPERTIES, 4)

        # Each property holds for a random 3-person subset. Three of five is
        # the source question's density and it is what makes the negations
        # discriminate — at 1 or 4 the query usually matches everyone or no one.
        sets = {name: set(rng.sample(people, 3)) for name, _ in props}

        # EVERY PERSON MUST APPEAR IN AT LEAST ONE STATEMENT. With 6 people and
        # 3 per property, someone can land in none of the four sets — they then
        # exist only as an option, which a student eliminates without reading
        # anything. Measured 436/3000 questions with such a phantom option; the
        # earlier "is this name in `people`" check missed it, because the name
        # WAS in people, just never printed.
        mentioned = set().union(*sets.values())
        if len(mentioned) < len(people):
            continue

        # Query: 2 negations + 1 positive, the source shape.
        chosen = rng.sample([p for p, _ in props], 3)
        query = [(chosen[0], False), (chosen[1], False), (chosen[2], True)]

        hits = [p for p in people if matches(p, query, sets)]
        if len(hits) != 1:
            continue                        # zero or ambiguous — unusable

        answer = hits[0]
        # Distractors: people who satisfy SOME of the query. A person who
        # satisfies none is eliminable at a glance, so prefer near-misses —
        # here that means genuinely partial matches, not arbitrary names.
        def score(p: str) -> int:
            return sum(1 for prop, want in query
                       if (p in sets[prop]) == want)
        others = sorted((p for p in people if p != answer),
                        key=lambda p: -score(p))
        # `bump=None` is load-bearing: without it distinct_wrongs falls back to
        # its numeric ladder and, when `others` is short, can emit a name that
        # appears in NO statement. Measured 436/3000 questions with a phantom
        # option — eliminable at a glance. The options must all be people the
        # student can actually see in the stem, so the candidate list is the
        # only source and a shortfall rejects the whole question.
        wrongs = distinct_wrongs(answer, others, rng, n=3,
                                 bump=lambda a, i: None)
        if len(wrongs) < 3 or any(w not in people for w in wrongs):
            continue
        break
    else:                                    # pragma: no cover
        people = ["कैलाश", "गोविन्द", "हरिन्दर", "राजेश", "जितेन्द्र"]
        props = _PROPERTIES[:4]
        sets = {
            "बुद्धिमान": {"कैलाश", "गोविन्द", "हरिन्दर"},
            "कठिन परिश्रमी": {"कैलाश", "राजेश", "जितेन्द्र"},
            "ईमानदार": {"राजेश", "हरिन्दर", "जितेन्द्र"},
            "महत्वाकांक्षी": {"कैलाश", "गोविन्द", "जितेन्द्र"},
        }
        query = [("ईमानदार", False), ("कठिन परिश्रमी", False),
                 ("महत्वाकांक्षी", True)]
        answer = "गोविन्द"
        wrongs = ["कैलाश", "राजेश", "हरिन्दर"]

    opts, letter = finish(answer, wrongs, rng)

    lines = []
    for i, (prop, phrase) in enumerate(props):
        members = [p for p in people if p in sets[prop]]
        rng.shuffle(members)
        lines.append(f"{_ROMAN[i]}. {', '.join(members[:-1])} और "
                     f"{members[-1]} {phrase} ।")
    stem = "यदि\n" + "\n".join(lines) + "\n" + _render_query(query)

    shown = ", ".join(f"{p}{'' if want else ' (नहीं)'}" for p, want in query)
    return {
        "stem": stem,
        "options": opts,
        "answer": letter,
        "format": "plain",
        # Intrinsic: more people means more rows to cross-check.
        # 5 people is the source question's own size — a candidate reads
        # four short rows. 6 is where the cross-checking gets real.
        "difficulty": "easy" if len(people) <= 5 else "moderate",
        "reason": f"शर्तें: {shown}; इन सभी को केवल {answer} पूरा करता है।",
        "_type": "grouping",
        "_dedup_key": "grouping:" + "|".join(
            f"{p}={','.join(sorted(sets[p]))}" for p, _ in props),
    }
