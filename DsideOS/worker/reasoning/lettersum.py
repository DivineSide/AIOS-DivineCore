# -*- coding: utf-8 -*-
"""lettersum — letter-value arithmetic, correct by construction.

MODELLED ON: vdo-vpdo 2023-12-31 Q95 —

    यदि अंग्रेज़ी वर्णमाला के प्रत्येक अक्षर का मान उसके वर्णमाला के क्रमांक के
    बराबर है, तो निम्न में से किसमें उसके सभी वर्णों का योग अधिकतम है ?
    (A) MATHS (B) STATS (C) HINDI (D) CIVIL          -> answer STATS

Verified: STATS = 19+20+1+20+19 = 79, MATHS = 61, HINDI = 46, CIVIL = 54.

WHY THIS IS THE SIMPLEST TYPE: the four options ARE the four words. There is no
distractor construction at all — the wrong options are simply the other three
words, which is why it needs no help from util.distinct_wrongs.

The only real constraint is that the winner must win STRICTLY. A tie makes the
question unanswerable, and with 4 random words a tie is not rare (measured ~3%
before the check), so `generate` resamples until the margin is clear.

Interface:
    generate(rng)      -> question dict
    letter_sum(word)   -> int          # pure, for tests
"""
from __future__ import annotations

import random

# Real English words, 4-6 letters, drawn from the register the papers use
# (school/exam vocabulary). Nonsense strings would let a candidate guess by
# shape; very long words make the mental arithmetic tedious rather than testing.
_WORDS = [
    "MATHS", "STATS", "HINDI", "CIVIL", "MUSIC", "PAPER", "WATER", "EARTH",
    "LIGHT", "NIGHT", "MONTH", "HOUSE", "TABLE", "CHAIR", "PLANT", "FRUIT",
    "RIVER", "OCEAN", "STONE", "METAL", "GLASS", "CLOTH", "BREAD", "SUGAR",
    "HEART", "BRAIN", "VOICE", "SOUND", "COLOR", "GREEN", "WHITE", "BLACK",
    "SMART", "QUICK", "BRAVE", "HAPPY", "QUIET", "SHARP", "YOUNG", "PROUD",
    "SCHOOL", "GARDEN", "MARKET", "WINTER", "SUMMER", "FLOWER", "FOREST",
    "SILVER", "GOLDEN", "STRONG", "BRIGHT", "PLANET", "ORANGE", "CANDLE",
]

# The two question forms the papers use. Both are answerable from the same
# computation; only the comparison direction differs.
_FORMS = [
    ("अधिकतम", max, "सर्वाधिक"),
    ("न्यूनतम", min, "सबसे कम"),
]

# Several phrasings, because a FIXED stem makes two questions of this type in
# one paper read as literal duplicates — the block-distinctness test caught
# exactly that. The word set varies the question; the phrasing varies the text.
_STEMS = [
    "यदि अंग्रेज़ी वर्णमाला के प्रत्येक अक्षर का मान उसके वर्णमाला के क्रमांक "
    "के बराबर है (A=1, B=2, … Z=26), तो निम्नलिखित में से किस शब्द के सभी "
    "अक्षरों का योग {word} है ?",
    "अंग्रेज़ी वर्णमाला में A=1, B=2, … Z=26 मानकर, नीचे दिए गए शब्दों में से "
    "किसके अक्षरों का कुल योग {word} होगा ?",
    "प्रत्येक अंग्रेज़ी अक्षर को उसका वर्णमाला क्रमांक (A=1 … Z=26) मान दिया "
    "गया है । निम्न में से किस शब्द का अक्षर-योग {word} है ?",
]


def letter_sum(word: str) -> int:
    """A=1 … Z=26, summed. O(len(word)).

    Independent of generate()'s path — the tests recompute with this and also
    by hand from ord(), so a bug here cannot hide behind itself.
    """
    return sum(ord(c.upper()) - ord("A") + 1 for c in word if c.isalpha())


def generate(rng: random.Random) -> dict:
    """One letter-value question. O(1) — bounded resampling.

    The four words ARE the four options, so there is no distractor step; the
    work is choosing a set whose extreme is unambiguous.
    """
    label, pick, _ = rng.choice(_FORMS)

    for _ in range(40):
        words = rng.sample(_WORDS, 4)
        sums = {w: letter_sum(w) for w in words}
        target = pick(sums.values())
        winners = [w for w, s in sums.items() if s == target]
        if len(winners) != 1:
            continue                       # a tie has no single right answer

        # Require a clear margin. A 1-point gap is technically answerable but
        # turns the question into a transcription-accuracy test rather than a
        # reasoning one, and invites disputes over a mis-added letter.
        others = sorted(s for w, s in sums.items() if w != winners[0])
        nearest = others[0] if label == "न्यूनतम" else others[-1]
        if abs(target - nearest) < 3:
            continue
        break
    else:                                   # pragma: no cover
        words = ["STATS", "MATHS", "CIVIL", "HINDI"]
        sums = {w: letter_sum(w) for w in words}
        label, pick = "अधिकतम", max
        winners = [max(sums, key=sums.get)]

    answer = winners[0]
    opts = list(words)
    rng.shuffle(opts)

    detail = ", ".join(f"{w}={sums[w]}" for w in opts)
    return {
        "stem": rng.choice(_STEMS).format(word=label),
        "options": opts,
        "answer": "abcd"[opts.index(answer)],
        "format": "plain",
        # Intrinsic: four 5-letter words is arithmetic everyone can do;
        # it gets harder only as the words lengthen.
        # Difficulty is the TOTAL arithmetic load, not one word's length: the
        # candidate sums all four. A length threshold alone collapsed this type
        # to a single level (every word in the pool is 5-7 letters), which is
        # worse than no tag at all — a type that is always "easy" cannot help
        # the paper hit its mix.
        "difficulty": ("easy" if sum(len(w) for w in words) <= 21 else
                       "moderate" if sum(len(w) for w in words) <= 24
                       else "hard"),
        "reason": f"अक्षर-मानों का योग: {detail}; अतः {label} योग "
                  f"{answer} ({sums[answer]}) का है।",
        "_type": "lettersum",
        # The WORD SET is the question; which form (max/min) was asked is part
        # of it, but the shuffle order is not.
        "_dedup_key": "lettersum:" + label + ":" + ",".join(sorted(words)),
    }
