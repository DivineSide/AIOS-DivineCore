# -*- coding: utf-8 -*-
"""triangles — "how many triangles are in this figure?", correct by construction.

THE MOST COMMON FIGURE TYPE in the real papers: 6 of the 8 figure PYQs
(corpus/reasoning-reference/SURVEY.md). Two constructions appear, and both are
implemented:

  STRIP      patwari-2023 p6, whose exact vector geometry was decoded from the
             text-native PDF: 4 verticals, 2 horizontals, 6 diagonals — a 1xN
             rectangle strip with both diagonals in every cell.
  TRIANGLE   vdo-vpdo 2023-07-09 Q26: an equilateral triangle subdivided into
             rows of small triangles.

HOW THE COUNT IS GUARANTEED. Not a formula. The figure is a set of SEGMENTS;
every unordered triple of segments is tested for whether it bounds a real
triangle — three pairwise intersections, all distinct, each lying within both
of its segments. That is O(n^3) in the segment count (n <= ~14, so a few
hundred checks) and it cannot be wrong for an unusual construction the way a
closed-form count can.

A formula was deliberately rejected: the strip and the subdivided triangle have
different formulas, extra chords break both, and a wrong formula produces a
wrong ANSWER KEY that no downstream gate can catch — the exact failure class
that bit coded_relations twice.

Interface:
    generate(rng)                -> question dict (with a `_figure` spec)
    count_triangles(segments)    -> int        # pure, for tests
"""
from __future__ import annotations

import random
from itertools import combinations

from .util import distinct_wrongs, finish

EPS = 1e-9

_STEMS = [
    "नीचे दी गई आकृति में कितने त्रिभुज हैं ?",
    "निम्न आकृति में त्रिभुजों की कुल संख्या कितनी है ?",
    "दी गई आकृति में बनने वाले त्रिभुजों की संख्या ज्ञात कीजिए ।",
]


def _intersect(s1, s2):
    """Intersection point of two segments, or None. O(1).

    Returns the point only when it lies WITHIN both segments (inclusive), so
    two segments that would cross if extended do not count.
    """
    (x1, y1), (x2, y2) = s1
    (x3, y3), (x4, y4) = s2
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < EPS:
        return None                      # parallel or collinear
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / den
    if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _same(p, q) -> bool:
    return abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6


def count_triangles(segments: list) -> int:
    """Exhaustive triangle count over a segment set. O(n^3).

    A triple bounds a triangle iff the three pairwise intersections all exist,
    are pairwise distinct, and are not collinear. Distinctness rules out three
    lines meeting at one point; the area check rules out collinear triples that
    somehow intersect pairwise.

    This is the INDEPENDENT re-derivation the tests use, and it is also what
    generate() calls — so the tests additionally recompute a known figure by
    hand (see test_triangles_matches_hand_counted_figure).
    """
    n = 0
    for a, b, c in combinations(segments, 3):
        p = _intersect(a, b)
        q = _intersect(b, c)
        r = _intersect(a, c)
        if p is None or q is None or r is None:
            continue
        if _same(p, q) or _same(q, r) or _same(p, r):
            continue
        area2 = abs((q[0] - p[0]) * (r[1] - p[1]) - (r[0] - p[0]) * (q[1] - p[1]))
        if area2 < 1e-9:
            continue
        n += 1
    return n


def _strip(cells: int, diagonals: str) -> list:
    """A 1 x `cells` rectangle strip. `diagonals` is "both" | "one" | "none".

    The patwari construction. Unit coordinates; the renderer maps them.
    """
    segs = [((0.0, 0.0), (1.0, 0.0)), ((0.0, 1.0), (1.0, 1.0))]
    for i in range(cells + 1):
        x = i / cells
        segs.append(((x, 0.0), (x, 1.0)))
    for i in range(cells):
        x0, x1 = i / cells, (i + 1) / cells
        if diagonals in ("both", "one"):
            segs.append(((x0, 0.0), (x1, 1.0)))
        if diagonals == "both":
            segs.append(((x1, 0.0), (x0, 1.0)))
    return segs


def _subdivided(rows: int) -> list:
    """An equilateral triangle cut into `rows` rows. The vdo-vpdo Q26 shape.

    Three families of parallel lines — one per side — which is what produces
    the familiar lattice of small upward and downward triangles.
    """
    apex, left, right = (0.5, 0.0), (0.0, 1.0), (1.0, 1.0)

    def lerp(p, q, t):
        return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)

    segs = [(apex, left), (apex, right), (left, right)]
    for i in range(1, rows):
        t = i / rows
        # Three families of parallels, one per side of the triangle.
        #
        # The base points are at 1-t, NOT t. A line through apex->left at
        # fraction t, drawn parallel to the RIGHT side, meets the base at
        # lerp(left, right, 1-t) — derived by following the right side's
        # direction down to y=1. Pairing it with lerp(left, right, t) instead
        # produced vertical lines and a crossing X rather than a lattice; the
        # render made it obvious, and the count came out 21 where a 3-row
        # triangle has 13.
        segs.append((lerp(apex, left, t), lerp(apex, right, t)))       # || base
        segs.append((lerp(apex, left, t), lerp(left, right, 1 - t)))   # || right
        segs.append((lerp(apex, right, t), lerp(right, left, 1 - t)))  # || left
    return segs


def generate(rng: random.Random) -> dict:
    """One triangle-counting question. O(n^3) with n <= ~14 segments."""
    if rng.random() < 0.5:
        cells = rng.choice([2, 3, 3, 4])
        diagonals = rng.choice(["both", "both", "one"])
        segments = _strip(cells, diagonals)
        shape = f"strip{cells}{diagonals}"
    else:
        rows = rng.choice([2, 3, 3, 4])
        segments = _subdivided(rows)
        shape = f"tri{rows}"

    answer = count_triangles(segments)
    if answer < 4:                            # too trivial to ask
        segments = _strip(3, "both")
        answer = count_triangles(segments)
        shape = "strip3both"

    # Distractors cluster TIGHTLY around the answer, as the real papers do —
    # 23/27/28/29 for a 27-triangle figure. A wide spread would let a candidate
    # eliminate by rough estimate instead of counting.
    cands = [answer + d for d in (1, -1, 2, -2, 3, -3, 4)]
    wrongs = distinct_wrongs(answer, [c for c in cands if c > 0], rng, n=3)

    opts, letter = finish(str(answer), [str(w) for w in wrongs], rng)

    return {
        "stem": rng.choice(_STEMS),
        "options": opts,
        "answer": letter,
        "format": "plain",
        # Intrinsic: more triangles means more to miss.
        "difficulty": ("easy" if answer <= 10 else
                       "moderate" if answer <= 22 else "hard"),
        "reason": (f"आकृति की सभी रेखाओं से बनने वाले त्रिभुजों की गणना करने "
                   f"पर कुल {answer} त्रिभुज प्राप्त होते हैं।"),
        "_type": "triangles",
        "_dedup_key": f"triangles:{shape}",
        "_figure": {"kind": "lines",
                    "segments": [[list(a), list(b)] for a, b in segments]},
    }
