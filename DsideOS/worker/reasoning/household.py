# -*- coding: utf-8 -*-
"""household — family-counting questions, correct by construction.

MODELLED ON: vdo-vpdo 2023-07-09 Q24 —

    एक संयुक्त परिवार में पिता, माता, 3 विवाहित पुत्र और एक अविवाहित पुत्री है।
    बेटों में से दो की 2-2 बेटियाँ हैं और एक का एक बेटा है। परिवार में कितने
    महिला सदस्य हैं ?          (A) 2 (B) 3 (C) 6 (D) 9      -> answer 6

    Check: माता + पुत्री + 3 पुत्रवधू? No — the sons' WIVES are not stated, so
    they are not counted. Females = माता(1) + अविवाहित पुत्री(1) + 2 sons x 2
    daughters(4) = 6. The keyed answer is right, and the trap is whether you
    invent wives for the married sons.

WHY THIS NEEDS ITS OWN STRUCTURE, not relations.py's tree: that tree is a fixed
single-instance shape keyed by relation word — one बहन, one भाई — with no way to
express "three sons", and its पुत्र/पुत्री nodes have no incoming edge at all.
Counting needs explicit multiplicity, so the household is built as a LIST OF
MEMBERS and the answer is a filter over that list. The description is rendered
from the same list, so the two cannot disagree.

THE DELIBERATE TRAP, preserved from the source: "विवाहित पुत्र" implies wives,
but the question never states them, so they are not members. The generator only
ever counts what it explicitly rendered.

Interface:
    generate(rng)          -> question dict
    count(members, sex)    -> int     # pure, for tests
"""
from __future__ import annotations

import random

from .util import distinct_wrongs, finish

# A member is (label, sex). Labels are for the reason line only — the count
# works on sex alone.
_M, _F = "m", "f"

_QUESTIONS = [
    ("महिला", _F, "परिवार में कितने महिला सदस्य हैं ?"),
    ("पुरुष", _M, "परिवार में कितने पुरुष सदस्य हैं ?"),
    (None, None, "परिवार में कुल कितने सदस्य हैं ?"),
]


def count(members: list[tuple[str, str]], sex: str | None) -> int:
    """Members of the given sex, or all when sex is None. O(len(members)).

    Independent of generate()'s rendering path — the tests rebuild the member
    list from the STEM text and call this.
    """
    if sex is None:
        return len(members)
    return sum(1 for _, s in members if s == sex)


def generate(rng: random.Random) -> dict:
    """One family-counting question. O(members) — a dozen at most.

    Builds the member list FIRST, renders the description from it, then counts.
    Every sentence in the stem corresponds to members that actually exist in
    the list, so the description can never overstate or understate the family.
    """
    members: list[tuple[str, str]] = [("पिता", _M), ("माता", _F)]
    clauses: list[str] = []

    n_sons = rng.randint(2, 4)
    n_daughters = rng.randint(1, 2)
    members += [(f"पुत्र{i+1}", _M) for i in range(n_sons)]
    members += [(f"पुत्री{i+1}", _F) for i in range(n_daughters)]

    married = rng.randint(1, n_sons)
    daughter_word = "पुत्री" if n_daughters == 1 else "पुत्रियाँ"
    unmarried = "अविवाहित " if rng.random() < 0.6 else ""
    clauses.append(
        f"पिता, माता, {married} विवाहित पुत्र"
        + (f" तथा {n_sons - married} अविवाहित पुत्र" if n_sons > married else "")
        + f" और {n_daughters} {unmarried}{daughter_word} हैं")

    # Grandchildren, attached to the married sons only. This is where the real
    # question gets its arithmetic, and where a candidate slips.
    gk_clauses = []
    n_gd = n_gs = 0
    if married >= 2 and rng.random() < 0.8:
        with_gd = rng.randint(1, married)
        per_gd = rng.randint(1, 2)
        n_gd = with_gd * per_gd
        members += [("पोती", _F)] * n_gd
        gk_clauses.append(f"विवाहित पुत्रों में से {with_gd} की "
                          f"{per_gd}-{per_gd} पुत्रियाँ हैं")
        rest = married - with_gd
        if rest >= 1 and rng.random() < 0.7:
            n_gs = rest
            members += [("पोता", _M)] * n_gs
            gk_clauses.append(f"तथा {rest} का एक-एक पुत्र है")
    if gk_clauses:
        clauses.append(" ".join(gk_clauses))

    label, sex, question = rng.choice(_QUESTIONS)
    answer = count(members, sex)

    # Distractors are the REAL slips this question invites:
    #   - counting the married sons' (never-stated) wives as members
    #   - forgetting the grandchildren entirely
    #   - counting only the eldest generation
    cands = [
        answer + married,                          # invented daughters-in-law
        answer - (n_gd if sex == _F else n_gs),    # grandchildren dropped
        count(members, sex) - 1,                   # off by one
        2 if sex is None else 1,                   # parents only
    ]
    wrongs = distinct_wrongs(answer, [c for c in cands if c > 0], rng, n=3)

    opts, letter = finish(str(answer), [str(w) for w in wrongs], rng)

    breakdown = f"{label + ' सदस्य' if label else 'कुल सदस्य'}: {answer}"
    return {
        "stem": "एक संयुक्त परिवार में " + " । ".join(clauses) + " । " + question,
        "options": opts,
        "answer": letter,
        "format": "plain",
        # Intrinsic: no grandchildren is a straight count; two
        # grandchild clauses means tracking three generations.
        "difficulty": ("easy" if not (n_gd or n_gs) else
                       "hard" if (n_gd and n_gs) else "moderate"),
        "reason": (f"परिवार में {n_sons} पुत्र, {n_daughters} पुत्री"
                   + (f", {n_gd} पोती" if n_gd else "")
                   + (f", {n_gs} पोता" if n_gs else "")
                   + f" तथा माता-पिता हैं; विवाहित पुत्रों की पत्नियों का "
                     f"उल्लेख नहीं है इसलिए उन्हें नहीं गिना जाता। "
                   + breakdown + " ।"),
        "_type": "household",
        "_dedup_key": (f"household:{n_sons},{n_daughters},{married},"
                       f"{n_gd},{n_gs},{sex}"),
    }
