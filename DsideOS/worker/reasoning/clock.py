# -*- coding: utf-8 -*-
"""clock — water-image and mirror-image of a clock face, correct by construction.

BUILT FROM FIRST PRINCIPLES, NOT FROM THE SOURCE QUESTION. vdo-vpdo 2023-12-31
Q91 is a clock water-image question, but its printed key is UNSOLVABLE: none of
its four List-II times is a correct water image of any List-I time, and the four
keyed pairings imply four different transformations (shifts of 120, 710, 560 and
520 minutes). The times were almost certainly garbled in OCR, or the original
showed clock FACES that the transcript rendered as digital times. Verified
2026-09-16 before writing this module.

So the maths here comes from the definition, which is unambiguous:

  WATER IMAGE — reflection in water below the clock, an UP-DOWN flip. The 12-6
  axis is fixed; 3 and 9 swap. A time t minutes past 12 becomes (720 - t).
      8:15 -> 495 min -> 720-495 = 225 -> 3:45

  MIRROR IMAGE — reflection in a vertical mirror beside the clock, a LEFT-RIGHT
  flip. The 3-9 axis is fixed; 12 and 6 swap. t becomes (360 - t) mod 720.
      8:15 -> 495 -> 360-495 = -135 -> 585 -> 9:45

Both are in the official syllabus (दर्पण प्रतिबिंब, जल प्रतिबिंब), and each is
the other's most confusable distractor — which is exactly what makes the
distractor set honest here.

EMITTED AS `plain`, not `match` (decided with Mayank): the real paper used
सूची-I/सूची-II with a कूट, but that sample is the broken one, and staying on
`plain` avoids routing the first reasoning type through formats.build("match").

Interface:
    generate(rng)        -> question dict
    water(h, m)          -> (h, m)     # pure, for tests
    mirror(h, m)         -> (h, m)     # pure, for tests
"""
from __future__ import annotations

import random

from .util import distinct_wrongs, finish

_KINDS = [
    ("जल प्रतिबिंब", "water"),
    ("दर्पण प्रतिबिंब", "mirror"),
]

_STEMS = [
    "यदि किसी घड़ी में समय {t} है, तो उसका {kind} क्या होगा ?",
    "एक घड़ी {t} का समय दिखा रही है । उसका {kind} कौन-सा समय दर्शाएगा ?",
    "घड़ी में {t} बजे हैं । इसका {kind} निम्नलिखित में से क्या होगा ?",
]

# Stems for the DRAWN variant: the time is shown on a dial instead of printed,
# which is the form the real papers use. The time must NOT appear in the text —
# that is the whole point of showing a face.
_FIGURE_STEMS = [
    "नीचे दी गई घड़ी में दर्शाये गये समय का {kind} कौन-सा होगा ?",
    "निम्न घड़ी में दिखाये गये समय का {kind} निम्नलिखित में से क्या होगा ?",
]


def _fmt(h: int, m: int) -> str:
    return f"{h}:{m:02d}"


def _to_min(h: int, m: int) -> int:
    return (h % 12) * 60 + m


def _from_min(t: int) -> tuple[int, int]:
    t %= 720
    return (t // 60) or 12, t % 60


def water(h: int, m: int) -> tuple[int, int]:
    """Water image: reflection about the 12-6 (vertical) axis. O(1).

    720 - t. Self-inverse: water(water(t)) == t, which the tests assert.
    """
    return _from_min(720 - _to_min(h, m))


def mirror(h: int, m: int) -> tuple[int, int]:
    """Mirror image: reflection about the 3-9 (horizontal) axis. O(1).

    360 - t (mod 720). Also self-inverse.
    """
    return _from_min(360 - _to_min(h, m))


def generate(rng: random.Random) -> dict:
    """One clock-image question. O(1).

    Avoids times ON an axis of symmetry (12:00, 6:00 for water; 3:00, 9:00 for
    mirror), where the image equals the original — a question whose answer is
    the time already printed in the stem is not a question.
    """
    kind_label, kind = rng.choice(_KINDS)
    fn = water if kind == "water" else mirror

    for _ in range(40):
        h = rng.randint(1, 12)
        m = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
        if (h, m) == fn(h, m):
            continue                       # fixed point — image == original
        break

    ah, am = fn(h, m)
    answer = _fmt(ah, am)

    # Distractors, each a REAL confusion:
    #   - the OTHER transformation (mirror when asked for water, and vice
    #     versa) — the single most common error on this topic
    #   - 12:00 minus the time computed without the hour borrow
    #   - an hour off, the classic slip when the minute hand crosses 12
    other = mirror(h, m) if kind == "water" else water(h, m)
    naive_h = (12 - h) if h != 12 else 12
    naive = _fmt(naive_h if naive_h else 12, (60 - m) % 60)
    off_hour = _fmt((ah % 12) + 1, am)

    # The ORIGINAL time must never be offered: a candidate eliminates "the
    # time already printed in the stem" without doing any work. It reaches the
    # candidate list through `naive` whenever 12-h happens to equal h.
    original = _fmt(h, m)
    cands = [_fmt(*other), naive, off_hour, _fmt((ah - 2) % 12 or 12, am)]
    wrongs = distinct_wrongs(answer, cands, rng, n=3, banned=[original],
                             bump=lambda a, i: None)
    if len(wrongs) < 3:                     # pragma: no cover
        pool = [_fmt(x, am) for x in range(1, 13)]
        wrongs = distinct_wrongs(answer, cands + pool, rng, n=3,
                                 banned=[original], bump=lambda a, i: None)

    opts, letter = finish(answer, wrongs, rng)

    rule = "720 − t" if kind == "water" else "360 − t"
    # Half the questions SHOW the dial rather than printing the time. Both
    # forms appear in the real papers, and the drawn one is the harder read —
    # the candidate must first tell the time off the face.
    as_figure = rng.random() < 0.5

    return {
        "stem": (rng.choice(_FIGURE_STEMS).format(kind=kind_label) if as_figure
                 else rng.choice(_STEMS).format(t=_fmt(h, m), kind=kind_label)),
        "options": opts,
        "answer": letter,
        "format": "plain",
        # Intrinsic: an exact hour needs no minute borrow; anything else
        # does, which is where candidates slip.
        # :00/:15/:30/:45 are the positions a candidate can picture on the
        # dial without arithmetic; the odd five-minute marks are where the
        # borrow actually has to be done.
        "difficulty": "easy" if m in (0, 15, 30, 45) else "moderate",
        "reason": (f"{kind_label} में घड़ी {'ऊपर-नीचे' if kind == 'water' else 'बाएँ-दाएँ'} "
                   f"पलट जाती है ({rule} मिनट); {_fmt(h, m)} का प्रतिबिंब "
                   f"{answer} है।"),
        "_type": "clock",
        # The drawn and printed forms of the same time are DIFFERENT questions
        # to a candidate, so they must not dedup against each other.
        "_dedup_key": f"clock:{kind}:{h}:{m:02d}:{'fig' if as_figure else 'txt'}",
        # Only the drawn variant carries a spec. figures._draw_clock renders the
        # dial from the same (h, m) the answer was computed from, so the face
        # and the key cannot disagree.
        **({"_figure": {"kind": "clock", "hour": h, "minute": m}}
           if as_figure else {}),
    }
