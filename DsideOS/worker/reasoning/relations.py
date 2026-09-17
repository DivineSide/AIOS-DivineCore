# -*- coding: utf-8 -*-
"""relations — Blood Relations questions, correct by construction.

MODELLED ON: vdo-vpdo 2023-12-31 Q93 (and its twin in the 2023-07-09 corpus) —

    एक महिला का परिचय कराते हुए राम ने कहा, "वह मेरी दादी की इकलौती संतान की
    पुत्री है।" महिला का राम से क्या सम्बन्ध है ?
    (A) माता (B) बहन (C) भतीजी (D) चचेरी बहन        -> answer बहन

The trick in the real question is "दादी की इकलौती संतान" — grandmother's ONLY
child must be the speaker's own father, so that child's daughter is the
speaker's sister. The word इकलौती (only) is load-bearing: without it the chain
is ambiguous and the question has no unique answer.

HOW THIS IS CORRECT BY CONSTRUCTION: a small family tree is built explicitly,
a path through it is chosen, and the relation is read off the tree. The stem is
the path rendered as nested possessives. Both the path and the answer come from
the same tree, so they cannot disagree.

Interface:
    generate(rng)          -> question dict
    resolve(tree, path)    -> relation label      # pure, for tests
"""
from __future__ import annotations

import random

from . import pools

# ── the family tree ─────────────────────────────────────────────────────────
# Three generations around a SPEAKER. Fixed shape, because the shape is what
# makes every chain unambiguous — a randomly-grown tree could produce
# "मेरे चाचा का पुत्र" with two valid answers.
#
#            दादा ── दादी
#                 │
#        ┌────────┴────────┐
#      पिता ── माता      चाचा ── चाची
#        │                  │
#   ┌────┴────┐         ┌───┴───┐
# SPEAKER   बहन/भाई   चचेरा भाई/बहन
#
# Each node: (id, generation, sex). Sex matters for BOTH the relation label and
# the name drawn for it — a node labelled पुत्री must never get a male name.
_NODES = {
    "दादा":        ("m", 0),
    "दादी":        ("f", 0),
    "पिता":        ("m", 1),
    "माता":        ("f", 1),
    "चाचा":        ("m", 1),
    "चाची":        ("f", 1),
    "self":       ("m", 2),
    "बहन":         ("f", 2),
    "भाई":         ("m", 2),
    "चचेरा भाई":    ("m", 2),
    "चचेरी बहन":    ("f", 2),
    "पुत्र":        ("m", 3),
    "पुत्री":       ("f", 3),
}

# Edges as (from, step, to). A "step" is the possessive phrase used in a stem.
# Only steps a real paper uses are included; "मेरे दादा के भाई" (grand-uncle)
# is real Hindi but never appears in these papers.
_EDGES = [
    ("self", "मेरे पिता", "पिता"),
    ("self", "मेरी माता", "माता"),
    ("self", "मेरी बहन", "बहन"),
    ("self", "मेरे भाई", "भाई"),
    ("पिता", "के पिता", "दादा"),
    ("पिता", "की माता", "दादी"),
    ("पिता", "के भाई", "चाचा"),
    ("माता", "के पति", "पिता"),
    ("दादी", "की इकलौती संतान", "पिता"),
    ("दादा", "की इकलौती संतान", "पिता"),
    ("चाचा", "की पत्नी", "चाची"),
    ("चाचा", "का पुत्र", "चचेरा भाई"),
    ("चाचा", "की पुत्री", "चचेरी बहन"),
    ("पिता", "की पुत्री", "बहन"),
    ("पिता", "का पुत्र", "भाई"),
    ("बहन", "की माता", "माता"),
    ("भाई", "के पिता", "पिता"),
]

# The answer vocabulary — how the terminal node relates back to the speaker.
# "भाई"/"बहन" as a TERMINAL means sibling; the same word as a STEP means
# something else ("मेरे पिता के भाई" = uncle), which is why steps and answers
# are separate tables.
_ANSWER = {
    "पिता": "पिता", "माता": "माता",
    "दादा": "दादा", "दादी": "दादी",
    "चाचा": "चाचा", "चाची": "चाची",
    "बहन": "बहन", "भाई": "भाई",
    "चचेरा भाई": "चचेरा भाई", "चचेरी बहन": "चचेरी बहन",
    "पुत्र": "पुत्र", "पुत्री": "पुत्री",
}

# Plausible wrong answers, grouped so a distractor is always the SAME KIND of
# relation as the answer (same generation, or an adjacent one). A distractor
# from a different generation is eliminable by inspection.
_CONFUSABLE = {
    "बहन":        ["भतीजी", "चचेरी बहन", "पुत्री", "माता"],
    "भाई":        ["भतीजा", "चचेरा भाई", "पुत्र", "पिता"],
    "चचेरी बहन":  ["बहन", "भतीजी", "पुत्री", "बुआ"],
    "चचेरा भाई":  ["भाई", "भतीजा", "पुत्र", "मामा"],
    "पिता":       ["चाचा", "दादा", "भाई", "मामा"],
    "माता":       ["चाची", "दादी", "बहन", "बुआ"],
    "चाचा":       ["पिता", "मामा", "दादा", "भाई"],
    "चाची":       ["माता", "बुआ", "दादी", "बहन"],
    "दादा":       ["पिता", "चाचा", "नाना", "मामा"],
    "दादी":       ["माता", "चाची", "नानी", "बुआ"],
}


def _walk(path: list[tuple[str, str, str]]) -> str:
    """The node a chain of edges lands on. O(len(path))."""
    return path[-1][2]


def resolve(path: list[tuple[str, str, str]]) -> str:
    """Relation of the path's endpoint to the speaker.

    Independent of generate()'s construction: the tests build a path, call
    this, and compare against the keyed answer.
    """
    return _ANSWER[_walk(path)]


def _paths_from(start: str, length: int, rng: random.Random
                ) -> list[tuple[str, str, str]] | None:
    """A random valid chain of `length` edges starting at `start`.

    Returns None if the walk dead-ends (a node with no outgoing edge in the
    table). Callers retry — cheaper than building a reachability index for a
    17-edge graph.

    Complexity: O(length * |_EDGES|).
    """
    path, node = [], start
    for _ in range(length):
        opts = [e for e in _EDGES if e[0] == node]
        # never immediately backtrack — "मेरे पिता की पुत्री की माता" is legal
        # but reads as nonsense
        if path:
            opts = [e for e in opts if e[2] != path[-1][0]]
        if not opts:
            return None
        edge = rng.choice(opts)
        path.append(edge)
        node = edge[2]
    return path


def generate(rng: random.Random) -> dict:
    """One Blood Relations question. O(1) — bounded retries on a tiny graph."""
    # REJECTION SAMPLING for a usable answer spread. Many edges lead to पिता,
    # so plain random walks answered "पिता" 43% of the time and "चाची" 0.6%
    # (measured over 3000 seeds). A paper whose relation questions are almost
    # always "father" tests one fact repeatedly. Common endpoints are resampled
    # a few times before being accepted, which flattens the distribution
    # without making any single question less valid.
    _COMMON = {"पिता", "माता"}
    path = answer = None
    for attempt in range(40):
        length = rng.choice([2, 2, 3])          # 2-step is the common real shape
        cand = _paths_from("self", length, rng)
        if not cand:
            continue
        got = resolve(cand)
        if got not in _CONFUSABLE:              # need a distractor pool
            continue
        # accept a common endpoint only on a later attempt, or by luck
        if got in _COMMON and attempt < 3 and rng.random() < 0.75:
            continue
        path, answer = cand, got
        break
    if path is None:                             # pragma: no cover
        path = [("self", "मेरे पिता", "पिता"), ("पिता", "की पुत्री", "बहन")]
        answer = "बहन"

    speaker_male = rng.random() < 0.7
    speaker = rng.choice(pools.MALE_NAMES if speaker_male
                         else pools.FEMALE_NAMES)

    # Render the chain: first step carries मेरे/मेरी, the rest are possessive.
    chain = path[0][1] + " " + " ".join(e[1] for e in path[1:])

    # Elder relations take the honorific plural in Hindi: "वह मेरे पिता के
    # पिता हैं", not "है". Getting this wrong is the kind of error a teacher
    # notices immediately even though the ANSWER is right.
    _ELDER = {"पिता", "माता", "दादा", "दादी", "चाचा", "चाची"}
    is_word = "हैं" if answer in _ELDER else "है"

    opener = rng.choice(pools.RELATION_OPENERS).format(name=speaker)
    closer = rng.choice(pools.RELATION_QUESTIONS).format(name=speaker)
    stem = f'{opener} "वह {chain} {is_word}।" {closer}'

    wrongs = [w for w in _CONFUSABLE[answer] if w != answer]
    rng.shuffle(wrongs)
    opts = [answer] + wrongs[:3]
    rng.shuffle(opts)
    idx = opts.index(answer)

    readable = " → ".join(e[2] for e in path)
    return {
        "stem": stem,
        "options": opts,
        "answer": "abcd"[idx],
        "format": "plain",
        # Intrinsic: chain length IS the difficulty of this type.
        "difficulty": "easy" if len(path) <= 2 else "moderate",
        "reason": f"सम्बन्ध शृंखला: {speaker} → {readable}; "
                  f"अतः वह {speaker} का/की {answer} है।",
        "_type": "relations",
        # The chain, not the rendered stem: the speaker's NAME is cosmetic, so
        # two questions on the same chain are the same question to a student.
        "_dedup_key": "relations:" + chain,
    }
