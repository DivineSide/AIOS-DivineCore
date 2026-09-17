# -*- coding: utf-8 -*-
"""coded_relations — relation-operator expressions, correct by construction.

MODELLED ON: vdo-vpdo 2023-07-09 Q25 —

    यदि A + B का अर्थ है A, B का बेटा है, A - B का अर्थ है A, B की पत्नी है,
    A × B का अर्थ है A, B का भाई है, तो P + R - Q का अर्थ होगा
    (A) Q, P का पिता है  (B) Q, P का बेटा है
    (C) Q, P की माँ है   (D) Q, P का भाई है

The expression reads LEFT TO RIGHT as a chain: `P + R` fixes P as R's son;
`R - Q` fixes R as Q's wife. So P is the son of Q's wife → Q is P's father.

WHY THIS DOES NOT REUSE relations.py's TREE: those edges are directional and
not closed under inverse — there is no edge back from पिता to self, and the
step PHRASES are written for one direction only ("मेरे पिता", "के भाई"). An
expression evaluator has to traverse both ways ("A is B's son" also tells you
"B is A's parent"), so it needs its own operator table where every operator
declares both directions. Sharing the other module's data would have meant
inverting phrases that were never written to be inverted.

HOW CORRECTNESS IS GUARANTEED: the chain is built from operators whose meaning
is declared as (role_of_left, role_of_right). Composing them yields the
relation of the last person to the first by pure lookup — the same composition
the candidate performs, run in code.

Interface:
    generate(rng)              -> question dict
    compose(chain)             -> str        # pure, for tests
"""
from __future__ import annotations

import random

from .util import distinct_wrongs, finish

# Operators, as (symbol, hindi_gloss, left_role, right_role).
# `left_role` is what the LEFT operand is to the RIGHT one.
_OPS = [
    ("+", "{a}, {b} का पुत्र है", "son", "parent"),
    ("-", "{a}, {b} की पत्नी है", "wife", "husband"),
    ("×", "{a}, {b} का भाई है", "brother", "sibling"),
    ("÷", "{a}, {b} की माता है", "mother", "child"),
]

# Composition table: (role of X to Y, role of Y to Z) -> role of X to Z.
# Only the compositions the generator can actually produce are listed; anything
# missing makes the chain unusable and is rejected, rather than guessed.
# EVERY ENTRY HERE IS HAND-VERIFIED. An earlier version contained
# ("wife", "son"): "mother" — wrong: if R is P's wife and P is S's son, R is
# S's daughter-in-law, not S's mother. It shipped a confidently wrong answer
# until a smoke test was read carefully. Only compositions that can be stated
# in one unambiguous word are listed; anything else is rejected by compose()
# returning None, which is safer than guessing.
_COMPOSE = {
    # X son of Y, Y wife/husband of Z  ->  X is Z's son (Z is a parent)
    ("son", "wife"): "son",
    ("son", "husband"): "son",
    # X son of Y, Y son of Z          ->  X is Z's grandson
    ("son", "son"): "grandson",
    # X son of Y, Y MOTHER of Z       ->  Y is Z's parent, so X and Z are
    # SIBLINGS. This was "grandson" until a hand-read of 100 generated
    # questions caught it (2026-09-16) — the SECOND wrong entry in this table,
    # after ("wife","son"). Direction is everything here: "Y son of Z" climbs
    # the tree, "Y mother of Z" descends it.
    ("son", "mother"): "sibling_of",
    # X brother of Y, Y son of Z       ->  X is also Z's son
    ("brother", "son"): "son",
    # X brother of Y, Y brother of Z   ->  X is Z's brother
    ("brother", "brother"): "brother",
    # X mother of Y, Y son of Z        ->  X is Z's wife
    ("mother", "son"): "wife_of",
    # X wife of Y, Y son of Z          ->  X is Z's daughter-in-law
    ("wife", "son"): "daughter_in_law",
}

# How the FIRST person relates to the LAST, phrased as the answer options do:
# "Q, P का पिता है" — i.e. the LAST person's relation to the FIRST.
# The LAST person's relation to the FIRST — the direction the options use.
# Particle matters: masculine relations take का, feminine take की. Getting it
# wrong ("N, R का माता है") is the kind of error a teacher spots instantly.
_INVERSE_LABEL = {
    "son": "{last}, {first} का पिता है",
    "grandson": "{last}, {first} का दादा है",
    "brother": "{last}, {first} का भाई है",
    "sibling_of": "{last}, {first} का भाई/बहन है",
    "wife_of": "{last}, {first} का पति है",
    "daughter_in_law": "{last}, {first} के ससुर हैं",
}

# Wrong options, grouped so a distractor is the same KIND of relation as the
# answer — a candidate must actually resolve the chain, not eliminate by shape.
# Wrong options as COMPLETE phrases (not bare words), so each carries its own
# correct particle. Same generation or adjacent, so nothing is eliminable by
# shape — the candidate has to resolve the chain.
_CONFUSABLE = {
    "son": ["{last}, {first} का पुत्र है", "{last}, {first} का भाई है",
            "{last}, {first} की माता है"],
    "grandson": ["{last}, {first} का पिता है", "{last}, {first} का चाचा है",
                 "{last}, {first} का भाई है"],
    "brother": ["{last}, {first} का पिता है", "{last}, {first} का पुत्र है",
                "{last}, {first} का चाचा है"],
    "sibling_of": ["{last}, {first} का पुत्र है", "{last}, {first} का पिता है",
                   "{last}, {first} का चाचा है"],
    "wife_of": ["{last}, {first} का पुत्र है", "{last}, {first} का भाई है",
                "{last}, {first} का पिता है"],
    "daughter_in_law": ["{last}, {first} के पिता हैं",
                        "{last}, {first} का पति है",
                        "{last}, {first} का भाई है"],
}

_LETTERS = ["P", "Q", "R", "S", "T", "M", "N"]

_STEMS = [
    "यदि {legend}, तो '{expr}' का अर्थ होगा —",
    "मान लीजिए {legend} । तब '{expr}' से क्या तात्पर्य है ?",
]


def compose(roles: list[str]) -> str | None:
    """Fold a chain of roles into one. O(len(roles)).

    Returns None when the chain has no defined composition — the caller
    rejects and resamples rather than inventing a relation.
    """
    cur = roles[0]
    for nxt in roles[1:]:
        cur = _COMPOSE.get((cur, nxt))
        if cur is None:
            return None
    return cur


def generate(rng: random.Random) -> dict:
    """One coded-relations question. O(1) — bounded resampling on a 2-op chain."""
    for _ in range(80):
        n_ops = 2                       # the source shape; 3 gets unreadable
        ops = [rng.choice(_OPS) for _ in range(n_ops)]
        people = rng.sample(_LETTERS, n_ops + 1)

        roles = [op[2] for op in ops]
        result = compose(roles)
        if result is None or result not in _INVERSE_LABEL:
            continue
        break
    else:                                # pragma: no cover
        ops = [_OPS[0], _OPS[1]]
        people = ["P", "R", "Q"]
        result = "son"

    expr = f" {ops[0][0]} ".join(people[:2]) + f" {ops[1][0]} " + people[2]

    # The legend declares every operator used, with fresh placeholder letters
    # so it reads as a definition rather than as part of the expression.
    legend_parts = []
    for sym, gloss, _, _ in {(o[0], o[1], o[2], o[3]) for o in ops}:
        legend_parts.append(f"'A {sym} B' का अर्थ है " + gloss.format(a="A", b="B"))
    legend = ", ".join(sorted(legend_parts))

    answer = _INVERSE_LABEL[result].format(first=people[0], last=people[-1])
    wrongs = [w.format(first=people[0], last=people[-1])
              for w in _CONFUSABLE[result]]
    wrongs = distinct_wrongs(answer, wrongs, rng, n=3, bump=lambda a, i: None)

    opts, letter = finish(answer, wrongs, rng)

    chain_txt = " → ".join(
        f"{people[i]} {ops[i][2]} of {people[i+1]}" for i in range(len(ops)))
    return {
        "stem": rng.choice(_STEMS).format(legend=legend, expr=expr),
        "options": opts,
        "answer": letter,
        "format": "plain",
        # Intrinsic: this type is inherently the harder end — two
        # operators must be decoded and then composed.
        "difficulty": "moderate" if result in ("son", "brother") else "hard",
        "reason": f"शृंखला: {chain_txt}; संयोजन से {answer}",
        "_type": "coded_relations",
        "_dedup_key": f"coded:{''.join(o[0] for o in ops)}:{result}",
    }
