# -*- coding: utf-8 -*-
"""coding — Coding-Decoding questions, correct by construction.

MODELLED ON two real questions:

  vdo-vpdo 2023-12-31 Q92:
    यदि शब्द "LEADER" का कोड 20-13-9-12-13-26 हो, तो "LIGHT" को कैसे लिखा जाए?
    -> the rule is (27 - alphabet position) + something; each letter maps to a
       number, joined by hyphens.

  police-constable 2025 Q37:
    'Q' को '5' से, 'SALT' को '28' से कूट किया गया है, तब 'SWEET' = ?
    -> positional SUM, a single number rather than a per-letter sequence.

So the type has two distinct output shapes — per-letter sequence and whole-word
sum — and both are implemented here.

WHY NO MODEL: the cipher is invented here, so applying it is mechanical. The
danger a model would introduce is precisely arithmetic slips over 5-6 letters.

SCRIPT NOTE: the source and target words are Latin (as in the real papers), but
the stem around them is Hindi. This passes validate_gen's Devanagari-majority
check comfortably (measured 0.69-0.72 against a 0.5 threshold) — though
reasoning bypasses that gate anyway. The words are quoted with spaces around
them so `_MIXED_SCRIPT` (which fires on Devanagari directly adjacent to Latin
with no space) can never trigger.

Interface:
    generate(rng)              -> question dict
    encode(word, rule, k)      -> str          # pure, for tests
"""
from __future__ import annotations

import random

from . import pools

# Source words. Real, common, 4-6 letters — a nonsense string would let a
# candidate guess the answer by pattern length alone, and a very long word
# makes the per-letter sequence unreadable in a two-column paper.
_WORDS = [
    "LEADER", "LIGHT", "SALT", "SWEET", "MOTHER", "FRIEND", "SCHOOL",
    "TEACHER", "GARDEN", "MARKET", "WINTER", "SILVER", "FOREST", "BRIGHT",
    "STRONG", "PLANET", "ORANGE", "CANDLE", "MODERN", "SIMPLE", "TRAVEL",
    "NUMBER", "LETTER", "SYSTEM", "FUTURE", "CIRCLE", "SQUARE", "FLOWER",
]

# (name, per_letter_fn, describe) — per_letter_fn(pos, k) -> int, where `pos`
# is the 1-based alphabet position of the letter.
#
# All four are INVERTIBLE and position-only: no rule depends on the letter's
# neighbours, so a candidate can verify any single letter independently. That
# is what makes the question fair, and it is also why `encode` can be a simple
# map rather than a stateful pass.
_RULES = [
    ("shift", lambda pos, k: pos + k,
     lambda k: f"प्रत्येक अक्षर के वर्णमाला क्रमांक में {k} जोड़ा गया है"),
    ("reverse", lambda pos, k: 27 - pos,
     lambda k: "प्रत्येक अक्षर को वर्णमाला में उसके विपरीत अक्षर "
               "(27 - क्रमांक) से बदला गया है"),
    ("double", lambda pos, k: pos * 2,
     lambda k: "प्रत्येक अक्षर के वर्णमाला क्रमांक को 2 से गुणा किया गया है"),
    ("reverse_shift", lambda pos, k: (27 - pos) + k,
     lambda k: f"प्रत्येक अक्षर को (27 - क्रमांक) से बदलकर {k} जोड़ा गया है"),
]


def _pos(ch: str) -> int:
    """1-based alphabet position. A=1 ... Z=26."""
    return ord(ch.upper()) - ord("A") + 1


def encode(word: str, rule_name: str, k: int, mode: str = "sequence") -> str:
    """Apply a cipher to a word. O(len(word)).

    mode="sequence" -> "20-13-9-12-13-26"   (per-letter, hyphen-joined)
    mode="sum"      -> "28"                 (positional total)

    This is the INDEPENDENT re-derivation the tests use; generate() calls it
    too, but the tests additionally recompute by hand from the rule table, so a
    bug inside encode cannot hide.
    """
    fn = next(f for nm, f, _ in _RULES if nm == rule_name)
    vals = [fn(_pos(c), k) for c in word]
    if mode == "sum":
        return str(sum(vals))
    return "-".join(str(v) for v in vals)


def _distractors(word: str, rule_name: str, k: int, mode: str,
                 answer: str, rng: random.Random) -> list[str]:
    """Three wrong codes, each produced by a REAL mis-application.

    - the neighbouring constant (k+1 / k-1)
    - a DIFFERENT rule from the table applied to the same word
    - the correct code with two adjacent values transposed (a transcription
      slip, and the one distractor that is genuinely hard to eliminate)

    Never random digits: a candidate who applies the rule correctly to even one
    letter can discard an off-pattern option instantly.
    """
    out: list[str] = []

    for dk in (1, -1):
        c = encode(word, rule_name, k + dk, mode)
        if c != answer and c not in out:
            out.append(c)

    for nm, _, _ in _RULES:
        if nm == rule_name:
            continue
        c = encode(word, nm, k, mode)
        if c != answer and c not in out:
            out.append(c)
            break

    if mode == "sequence":
        parts = answer.split("-")
        if len(parts) >= 2:
            i = rng.randrange(len(parts) - 1)
            swapped = parts[:]
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
            c = "-".join(swapped)
            if c != answer and c not in out:
                out.append(c)

    bump = 1
    while len(out) < 3:
        if mode == "sum":
            c = str(int(answer) + bump)
        else:
            parts = answer.split("-")
            parts[-1] = str(int(parts[-1]) + bump)
            c = "-".join(parts)
        if c != answer and c not in out:
            out.append(c)
        bump += 1
    return out[:3]


def generate(rng: random.Random) -> dict:
    """One Coding-Decoding question. O(len(word)).

    Picks two DIFFERENT words — one to demonstrate the cipher, one to ask
    about. Using the same word for both would make the answer copyable from
    the stem.
    """
    rule_name, fn, describe = rng.choice(_RULES)
    k = rng.randint(1, 5) if rule_name in ("shift", "reverse_shift") else 0
    mode = "sum" if rng.random() < 0.25 else "sequence"

    src, dst = rng.sample(_WORDS, 2)
    # Keep the rendered sequence readable in a two-column layout.
    while mode == "sequence" and (len(src) > 6 or len(dst) > 6):
        src, dst = rng.sample(_WORDS, 2)

    src_code = encode(src, rule_name, k, mode)
    answer = encode(dst, rule_name, k, mode)

    wrongs = _distractors(dst, rule_name, k, mode, answer, rng)
    opts = [answer] + wrongs
    rng.shuffle(opts)
    idx = opts.index(answer)

    stem = rng.choice(pools.CODING_QUESTIONS).format(
        src=src, code=src_code, dst=dst)

    return {
        "stem": stem,
        "options": opts,
        "answer": "abcd"[idx],
        "format": "plain",
        # Intrinsic: a plain shift is spotted immediately; a reversed
        # alphabet with an offset, or a positional SUM (which hides the
        # per-letter mapping), takes real work.
        "difficulty": ("easy" if rule_name == "shift" else
                       "hard" if (rule_name == "reverse_shift" or mode == "sum")
                       else "moderate"),
        "reason": f"{describe(k)}; अतः '{dst}' का कूट {answer} होगा।",
        "_type": "coding",
    }
