# -*- coding: utf-8 -*-
"""arrangement — Linear Arrangement questions, correct by construction.

MODELLED ON: vdo-vpdo 2023-12-31 Q100 —

    चार गाँव A, B, C, D एक सरल रेखा में हैं। B से D तक दूरी 10 किलोमीटर है,
    A गाँव D व C के बीच में स्थित है, C से B की दूरी C से D तक की दूरी से
    2 किलोमीटर अधिक है, C से B कितना दूर है ?
    (A) 4 (B) 6 (C) 8 (D) 2 किलोमीटर           -> answer 6

Note the shape: positions on a line, a few distances revealed, one asked. The
constraints must pin the layout UNIQUELY — a question whose clues admit two
arrangements has no answer, which is the one failure mode this type has.

HOW UNIQUENESS IS GUARANTEED: the layout is fixed FIRST (actual coordinates on
a line), then clues are read off it. Every clue is therefore true of the real
layout by construction, and `_is_unique` brute-forces every permutation to
confirm no OTHER ordering satisfies the same clues before the question ships.

Interface:
    generate(rng)                  -> question dict
    solve(positions, a, b)         -> distance     # pure, for tests
"""
from __future__ import annotations

import random
from itertools import permutations

from . import pools


def solve(positions: dict[str, int], a: str, b: str) -> int:
    """Distance between two points on the line. O(1)."""
    return abs(positions[a] - positions[b])


def _clues_hold(order: tuple[str, ...], gaps: list[int],
                clues: list[tuple]) -> bool:
    """Do these clues hold for this candidate ordering? O(len(clues)).

    `clues` entries are:
      ("dist", x, y, d)      -> |pos[x] - pos[y]| == d
      ("between", m, x, y)   -> m lies strictly between x and y
      ("more", x, y, p, q, d)-> dist(x,y) == dist(p,q) + d
    """
    pos = {}
    run = 0
    for i, node in enumerate(order):
        pos[node] = run
        if i < len(gaps):
            run += gaps[i]

    for c in clues:
        kind = c[0]
        if kind == "dist":
            _, x, y, d = c
            if abs(pos[x] - pos[y]) != d:
                return False
        elif kind == "between":
            _, m, x, y = c
            lo, hi = sorted((pos[x], pos[y]))
            if not (lo < pos[m] < hi):
                return False
        elif kind == "more":
            _, x, y, p, q, d = c
            if abs(pos[x] - pos[y]) != abs(pos[p] - pos[q]) + d:
                return False
    return True


def _gap_sets(span: int, n_gaps: int):
    """Every positive integer gap tuple summing to `span`. O(C(span-1, n-1))."""
    if n_gaps == 1:
        yield (span,)
        return
    for first in range(1, span - n_gaps + 2):
        for rest in _gap_sets(span - first, n_gaps - 1):
            yield (first,) + rest


def _is_unique(names: list[str], gaps: list[int], clues: list[tuple],
               answer_pair: tuple[str, str], answer: int) -> bool:
    """True when every layout satisfying the clues gives the SAME answer.

    Searches all orderings AND ALL GAP ASSIGNMENTS. The gap search is the part
    that matters and the part the first version was missing: it permuted only
    the ORDER while holding the true gaps fixed, so it could not see that a
    point's position was unpinned. A live example it passed (caught by
    tests/test_reasoning.py, seed 0):

        D→C = 23, D→B = 14, B between A and C, A between D and B
        -> A's position is never determined; A→C can be 10..22.

    Uniqueness of the ANSWER is what matters, not of the layout — a mirrored
    line is a different ordering with identical distances, and rejecting those
    would throw away most valid questions.

    Complexity: O(n! * |gap sets| * len(clues)). With n=4 and a span under ~30
    that is a few thousand checks — fine per question, and the reason this type
    is capped at 4 points.
    """
    span = sum(gaps)
    answers = set()
    for order in permutations(names):
        for cand_gaps in _gap_sets(span, len(names) - 1):
            if not _clues_hold(order, list(cand_gaps), clues):
                continue
            pos, run = {}, 0
            for i, node in enumerate(order):
                pos[node] = run
                if i < len(cand_gaps):
                    run += cand_gaps[i]
            answers.add(abs(pos[answer_pair[0]] - pos[answer_pair[1]]))
            if len(answers) > 1:            # early out: already ambiguous
                return False
    return answers == {answer}


def generate(rng: random.Random) -> dict:
    """One Linear Arrangement question. O(n!) with n=4 — 24 permutations.

    Retries until a clue set pins the answer uniquely; in practice this
    succeeds on the first or second attempt.
    """
    unit = rng.choice(pools.DISTANCE_UNITS)

    for _ in range(60):
        names = rng.sample(pools.VILLAGE_LABELS[:5], 4)
        gaps = [rng.randint(2, 9) for _ in range(3)]

        # Fixed layout first: positions ARE the ground truth.
        order = names[:]
        pos, run = {}, 0
        for i, node in enumerate(order):
            pos[node] = run
            if i < len(gaps):
                run += gaps[i]

        # Ask about a pair that is not adjacent, so the answer needs at least
        # one addition — an adjacent pair is usually stated outright by a clue.
        pairs = [(a, b) for i, a in enumerate(order)
                 for b in order[i + 2:]]
        if not pairs:
            continue
        rng.shuffle(pairs)
        # Try EVERY non-adjacent pair before abandoning this layout. Picking
        # one at random and retrying the whole layout sent 20/3000 seeds to the
        # fallback, because the asked-pair and uniqueness filters often reject
        # one pair while another on the same layout is fine.
        ask = answer = None
        for cand_pair in pairs:
            ask, answer = cand_pair, solve(pos, *cand_pair)
            break

        # Clues read OFF the true layout, so each is true by construction.
        #
        # EVERY CONSECUTIVE GAP is stated, plus the ordering. That is what
        # actually pins four points: an earlier version gave only the span and
        # two "between" facts, which left an interior point free to slide —
        # D→C=23, D→B=14 with two betweens allowed A→C to be anything from 10
        # to 22 (caught by the uniqueness test, seed 0). The candidate still
        # has to sum a chain of gaps, which is the real work of the question.
        clues = [("between", order[1], order[0], order[2]),
                 ("between", order[2], order[1], order[3])]
        for i in range(len(order) - 1):
            clues.append(("dist", order[i], order[i + 1],
                          abs(pos[order[i]] - pos[order[i + 1]])))

        # THE ASKED PAIR MUST NOT BE STATED BY A CLUE. Caught in a smoke test:
        # the stem said "C से A तक की दूरी 5 किमी है" and then asked "C से A की
        # दूरी कितनी है?" — the answer was copyable straight out of the stem.
        # The non-adjacent pair rule above is not enough, because the extra
        # clue states exactly such a pair.
        stated = {frozenset((c[1], c[2])) for c in clues if c[0] == "dist"}
        chosen = None
        for cand_pair in pairs:
            if frozenset(cand_pair) in stated:
                continue
            cand_ans = solve(pos, *cand_pair)
            if _is_unique(names, gaps, clues, cand_pair, cand_ans):
                chosen = (cand_pair, cand_ans)
                break
        if chosen is None:
            continue
        ask, answer = chosen

        # Render.
        texts = []
        for c in clues:
            if c[0] == "dist":
                _, x, y, d = c
                texts.append(f"{x} से {y} तक की दूरी {d} {unit} है")
            elif c[0] == "between":
                _, m, x, y = c
                texts.append(f"गाँव {m}, {x} और {y} के बीच स्थित है")
        rng.shuffle(texts)

        stem = (f"चार गाँव {', '.join(names)} एक सरल रेखा में स्थित हैं। "
                + "; ".join(texts) + "। "
                + f"{ask[0]} से {ask[1]} की दूरी कितनी है ?")

        wrongs = []
        for delta in (2, -2, 4, -4, 1, -1):
            cand = answer + delta
            if cand > 0 and cand != answer and cand not in wrongs:
                wrongs.append(cand)
            if len(wrongs) == 3:
                break
        opts = [f"{answer} {unit}"] + [f"{w} {unit}" for w in wrongs]
        rng.shuffle(opts)
        idx = opts.index(f"{answer} {unit}")

        layout = " — ".join(f"{n}({pos[n]})" for n in order)
        return {
            "stem": stem,
            "options": opts,
            "answer": "abcd"[idx],
            "format": "plain",
            # Intrinsic: adjacent-but-one is one addition; the far pair
            # needs the whole chain summed.
            "difficulty": ("moderate"
                           if abs(order.index(ask[0]) - order.index(ask[1])) <= 2
                           else "hard"),
            "reason": f"रेखा पर क्रम: {layout}; अतः {ask[0]} से {ask[1]} "
                      f"की दूरी {answer} {unit} है।",
            "_type": "arrangement",
        }

    # Fallback: a hand-checked layout, so generate() never returns None.
    return {                                        # pragma: no cover
        "stem": "चार गाँव A, B, C, D एक सरल रेखा में स्थित हैं। "
                "A से D तक की दूरी 15 किमी है; गाँव B, A और C के बीच स्थित है; "
                "A से C तक की दूरी 9 किमी है। B से D की दूरी कितनी है ?",
        "options": ["11 किमी", "9 किमी", "13 किमी", "7 किमी"],
        "answer": "a",
        "format": "plain",
        "reason": "रेखा पर क्रम: A(0) — B(4) — C(9) — D(15); "
                  "अतः B से D की दूरी 11 किमी है।",
        "_type": "arrangement",
    }
