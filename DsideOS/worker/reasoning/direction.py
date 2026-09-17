# -*- coding: utf-8 -*-
"""direction — Direction & Distance questions, correct by construction.

MODELLED ON: vdo-vpdo 2023-07-09 Q23 (corpus/reasoning-reference/.../page6.png):

    योगेश ने पूर्व दिशा में चलना प्रारम्भ किया। 2 km चलने के बाद वह दक्षिण
    दिशा में मुड़कर 5 km चला। पुनः वह पूर्व दिशा में मुड़कर 1 km चला। अंत में
    वह उत्तर दिशा में मुड़कर 9 km चला। अपने प्रारम्भिक बिन्दु से वह कितनी दूर है?
    (A) 3 km  (B) 4 km  (C) 5 km  (D) 7 km        -> answer 5

Note what the real distractors are: East displacement is 2+1 = 3, North is
9-5 = 4, answer is 5. **3 and 4 are the legs of the right triangle** — they are
the partial results a candidate gets by stopping early, not random near-misses.
_distractors() reproduces exactly that.

WHY NO MODEL: the walk is invented here, so the endpoint is arithmetic, not a
fact about the world. `solve()` is a re-derivation used by the tests to check
`generate()` against an independent path.

Interface:
    generate(rng) -> question dict (stem, options, answer, format, reason)
    solve(legs)   -> (dx, dy, distance)      # pure, for tests
"""
from __future__ import annotations

import math
import random

from . import pools

# Pythagorean triples whose legs are reachable by a 4-leg walk. Using a triple
# guarantees an INTEGER answer — a walk with an irrational displacement
# ("√29 किमी") is not something a UKSSSC paper ever asks.
# Complexity note: this is a fixed table, not a search; picking a triple first
# and deriving the walk from it is O(1) and cannot fail, whereas picking random
# legs and hoping for an integer hypotenuse would reject ~95% of attempts.
_TRIPLES = [(3, 4, 5), (6, 8, 10), (5, 12, 13), (8, 15, 17),
            (9, 12, 15), (12, 16, 20), (7, 24, 25), (4, 3, 5)]


def solve(legs: list[tuple[str, int]]) -> tuple[int, int, float]:
    """Net displacement and straight-line distance for a walk.

    `legs` is [(direction_label, distance), ...] using pools.DIRECTIONS.
    Returns (dx, dy, distance). O(len(legs)).

    This is the INDEPENDENT re-solve the tests compare against — it must not
    share code with the construction path in generate(), or a bug in the shared
    part would cancel out and the test would pass on wrong output.
    """
    dx = dy = 0
    for label, dist in legs:
        ux, uy = pools.DIRECTIONS[label]
        dx += ux * dist
        dy += uy * dist
    return dx, dy, math.hypot(dx, dy)


def _build_walk(rng: random.Random) -> tuple[list[tuple[str, int]], int, int, int]:
    """Construct a 4-leg walk whose net displacement is a chosen triple.

    Returns (legs, |dx|, |dy|, distance). The walk is built BACKWARDS from the
    answer: pick the triple, split each axis into an out-leg and a back-leg so
    the path doubles back (which is what makes the question non-trivial), then
    interleave the axes.
    """
    a, b, c = rng.choice(_TRIPLES)

    # Split each axis: net `a` East = (a + back) East then `back` West.
    # back >= 1 so the walk genuinely reverses on both axes.
    back_x = rng.randint(1, 6)
    back_y = rng.randint(1, 6)

    east_label = rng.choice(["पूर्व", "पश्चिम"])
    west_label = "पश्चिम" if east_label == "पूर्व" else "पूर्व"
    north_label = rng.choice(["उत्तर", "दक्षिण"])
    south_label = "दक्षिण" if north_label == "उत्तर" else "उत्तर"

    # Order: out-x, out-y(+back), back-x, ... interleaved so consecutive legs
    # are always perpendicular — two same-axis legs in a row would let a
    # candidate merge them by inspection.
    legs = [
        (east_label, a + back_x),
        (south_label, back_y),
        (west_label, back_x),
        (north_label, b + back_y),
    ]
    return legs, a, b, c


def _distractors(dx: int, dy: int, dist: int, rng: random.Random) -> list[int]:
    """The three wrong answers, each a REAL mistake a candidate makes.

    Not random near-misses: |dx| and |dy| are what you get by tracking only one
    axis, and |dx|+|dy| is the Manhattan distance (forgetting to apply
    Pythagoras). This mirrors the real paper, where 3 and 4 flank the true 5.

    Returns exactly 3 distinct ints, none equal to `dist`. Falls back to
    near-misses only if the natural three collide (possible on small triples).
    """
    cands = [abs(dx), abs(dy), abs(dx) + abs(dy)]
    out: list[int] = []
    for c in cands:
        if c != dist and c > 0 and c not in out:
            out.append(c)
    # Top up if the structural distractors collided (e.g. dx == dy).
    bump = 1
    while len(out) < 3:
        for cand in (dist + bump, dist - bump):
            if cand > 0 and cand != dist and cand not in out:
                out.append(cand)
                if len(out) == 3:
                    break
        bump += 1
    return out[:3]


def generate(rng: random.Random) -> dict:
    """One Direction & Distance question. No I/O, no model.

    Complexity: O(1) — fixed 4-leg walk, fixed 4 options.
    """
    legs, a, b, c = _build_walk(rng)
    dx, dy, dist_f = solve(legs)
    dist = int(round(dist_f))

    female = rng.random() < 0.35            # real papers are male-dominated
    name = rng.choice(pools.FEMALE_NAMES if female else pools.MALE_NAMES)
    verb = rng.choice(pools.WALK_VERBS_F if female else pools.WALK_VERBS_M)
    unit = rng.choice(pools.DISTANCE_UNITS)
    turn = rng.choice(pools.TURN_WORDS)

    first_dir, first_dist = legs[0]
    parts = [f"{name} ने {first_dir} दिशा में {first_dist} {unit} चलना "
             f"प्रारम्भ किया।"]
    connectors = ["इसके बाद वह", "फिर वह", "पुनः वह", "अंत में वह"]
    for i, (label, dist_i) in enumerate(legs[1:], 1):
        conn = connectors[min(i, len(connectors) - 1)]
        parts.append(f"{conn} {label} दिशा में {turn} {dist_i} {unit} {verb}।")
    stem = " ".join(parts) + " " + rng.choice(pools.DISTANCE_QUESTIONS)

    wrongs = _distractors(dx, dy, dist, rng)
    opts = [f"{dist} {unit}"] + [f"{w} {unit}" for w in wrongs]
    rng.shuffle(opts)
    idx = opts.index(f"{dist} {unit}")

    return {
        "stem": stem,
        "options": opts,
        "answer": "abcd"[idx],
        "format": "plain",
        # Intrinsic: a triple with small legs (3-4-5) is mental arithmetic;
        # 7-24-25 or 8-15-17 needs working out.
        # 3-4-5 and 6-8-10 are the triples every candidate recognises on
        # sight; 5-12-13 / 9-12-15 need the sum; the rest need real work.
        "difficulty": ("easy" if c <= 10 else
                       "moderate" if c <= 15 else "hard"),
        "reason": (f"पूर्व-पश्चिम विस्थापन {abs(dx)} {unit}, "
                   f"उत्तर-दक्षिण विस्थापन {abs(dy)} {unit}; "
                   f"अतः दूरी = √({abs(dx)}² + {abs(dy)}²) = {dist} {unit}।"),
        "_type": "direction",
    }
