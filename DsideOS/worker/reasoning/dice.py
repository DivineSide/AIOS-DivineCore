# -*- coding: utf-8 -*-
"""dice — "what is on the bottom face?", correct by construction.

MODELLED ON: vdo-vpdo 2023-07-09 Q21 — see the real figure at
corpus/reasoning-reference/vdo-vpdo-2023-07-09/page5.png. Three isometric
cubes, each showing top / front-left / front-right, and the question asks the
bottom face of each.

VERIFIED FROM THE REAL PAPER before building. Views (5,1,2), (5,3,6), (5,2,3):
the faces seen ADJACENT to 5 are {1,2,3,6}, so the only face that can be
opposite 5 is 4; and since 5 is on top in all three views the bottom is 4 every
time. That derivation is the whole method. (The printed options read "4,4,6",
whose third value contradicts it — the same OCR damage seen on Q91's clock key.
We build from the derivation, not from the printed key.)

HOW IT IS CORRECT BY CONSTRUCTION: the three opposite-face PAIRS are chosen
first, so "what is opposite X" is settled before any view exists. Views are
then generated as genuine rotations of that die, and the answer is read
straight off the pairing. The picture and the answer come from the same object.

THE CONSTRAINT THAT MAKES IT SOLVABLE: a candidate can only deduce the pairing
from what the views SHOW. So the views must, between them, reveal enough — for
a top face T, every one of the four faces adjacent to T must appear somewhere,
leaving exactly one candidate for the bottom. `_is_solvable` enforces that
before the question ships; without it the question would have several valid
answers and no runtime gate would catch it.

Interface:
    generate(rng)              -> question dict (with a `_figure` spec)
    opposite(pairs, face)      -> int        # pure, for tests
    solvable(views)            -> bool       # pure, for tests
"""
from __future__ import annotations

import random

from .util import distinct_wrongs, finish

_FACES = (1, 2, 3, 4, 5, 6)

_STEMS = [
    "एक ही पासे की निम्न तीन भिन्न स्थितियों में उसके निचले तल पर कौन-से अंक "
    "आयेंगे ?",
    "नीचे एक ही पासे की तीन स्थितियाँ दिखाई गई हैं । प्रत्येक स्थिति में "
    "पासे के निचले तल पर कौन-सा अंक होगा ?",
    "एक पासे की तीन विभिन्न स्थितियाँ नीचे दी गई हैं । तीनों स्थितियों में "
    "निचले तल के अंक क्रमशः क्या होंगे ?",
]


def opposite(pairs: list[tuple[int, int]], face: int) -> int:
    """The face opposite `face`. O(3).

    Independent of generate()'s construction — the tests build a die, ask this,
    and compare against the keyed answer.
    """
    for a, b in pairs:
        if a == face:
            return b
        if b == face:
            return a
    raise ValueError(f"face {face} is not in {pairs}")


def solvable(views: list[tuple[int, int, int]]) -> bool:
    """Can the bottom faces be deduced from these views alone? O(views).

    For each view's top face T, the four faces adjacent to T must all be
    visible somewhere across the views — only then is exactly one face left as
    the opposite of T. If two or more remain, the question has multiple valid
    answers.

    This is the same discipline arrangement.py needed: an ambiguous question is
    structurally perfect and semantically broken, so nothing downstream catches
    it.
    """
    seen: dict[int, set[int]] = {}
    for top, left, right in views:
        seen.setdefault(top, set()).update({left, right})
    for top, adj in seen.items():
        remaining = set(_FACES) - adj - {top}
        if len(remaining) != 1:
            return False
    return True


def _rotations(pairs: list[tuple[int, int]], rng: random.Random
               ) -> list[tuple[int, int, int]]:
    """Three (top, left, right) views of one die, all genuinely consistent.

    A view is legal iff no two visible faces are opposite each other — that is
    what makes it a real rotation rather than an impossible die.
    """
    def legal(t: int, l: int, r: int) -> bool:
        return (opposite(pairs, t) not in (l, r)
                and opposite(pairs, l) != r
                and len({t, l, r}) == 3)

    out = []
    for _ in range(200):
        t = rng.choice(_FACES)
        cands = [f for f in _FACES if f != t and opposite(pairs, t) != f]
        rng.shuffle(cands)
        for l in cands:
            rs = [f for f in cands if f != l and legal(t, l, f)]
            if rs:
                out.append((t, l, rng.choice(rs)))
                break
        if len(out) == 3:
            break
    return out


def generate(rng: random.Random) -> dict:
    """One dice question. O(1) — bounded resampling on a 6-face die.

    The stem asks for the bottom of each of three views, so the answer is a
    triple like "4, 2, 6" — which is exactly how the real paper words it.
    """
    for _ in range(60):
        faces = list(_FACES)
        rng.shuffle(faces)
        pairs = [(faces[0], faces[1]), (faces[2], faces[3]), (faces[4], faces[5])]

        views = _rotations(pairs, rng)
        if len(views) != 3 or not solvable(views):
            continue

        bottoms = [opposite(pairs, t) for t, _, _ in views]
        break
    else:                                    # pragma: no cover
        pairs = [(5, 4), (1, 6), (2, 3)]
        views = [(5, 1, 2), (5, 3, 6), (5, 2, 3)]
        bottoms = [4, 4, 4]

    answer = ", ".join(str(b) for b in bottoms)

    # Distractors are REAL mistakes, not random triples:
    #   - reading the TOP faces instead of the bottoms
    #   - assuming opposite faces sum to 7 (true of a standard die, but this
    #     die's pairing is given by the views — the classic trap)
    #   - one bottom wrong, the rest right (a single mis-deduction)
    cands = [
        ", ".join(str(t) for t, _, _ in views),
        ", ".join(str(7 - t) for t, _, _ in views),
        ", ".join(str(b if i else opposite(pairs, views[0][1]))
                  for i, b in enumerate(bottoms)),
        ", ".join(str(v[1]) for v in views),
    ]
    wrongs = distinct_wrongs(answer, cands, rng, n=3, bump=lambda a, i: None)
    if len(wrongs) < 3:                      # pragma: no cover
        pool = [", ".join(str(rng.choice(_FACES)) for _ in views)
                for _ in range(12)]
        wrongs = distinct_wrongs(answer, cands + pool, rng, n=3,
                                 bump=lambda a, i: None)

    opts, letter = finish(answer, wrongs, rng)

    pair_txt = ", ".join(f"{a}-{b}" for a, b in pairs)
    return {
        "stem": rng.choice(_STEMS),
        "options": opts,
        "answer": letter,
        "format": "plain",
        # Intrinsic: HOW MANY VIEWS the candidate must combine before the
        # bottom is forced. With two views the four neighbours are already
        # revealed and the deduction is immediate; needing all three means
        # holding more in mind.
        #
        # Keying off "how many distinct top faces" was tried first and made
        # every question easy — solvable() requires all four neighbours of a
        # top to be shown, which three views can only manage when they SHARE a
        # top, so that count is always 1. Caught by
        # test_difficulty_actually_varies, which exists for exactly this.
        "difficulty": ("easy" if solvable(views[:2]) else
                       "moderate" if len(set(sum(([v[1], v[2]] for v in views),
                                                 []))) <= 4
                       else "hard"),
        "reason": (f"दृश्य फलकों से सम्मुख युग्म {pair_txt} प्राप्त होते हैं; "
                   f"अतः निचले तल क्रमशः {answer} होंगे।"),
        "_type": "dice",
        "_dedup_key": "dice:" + "|".join(f"{t}{l}{r}" for t, l, r in views),
        # The SPEC, not a file. render.py turns this into figs/qN.png; nothing
        # here touches disk (see reasoning/__init__.py's purity note).
        "_figure": {"kind": "dice", "views": [list(v) for v in views]},
    }
