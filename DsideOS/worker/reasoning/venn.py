# -*- coding: utf-8 -*-
"""venn — "which diagram fits this description?", correct by construction.

MODELLED ON: vdo-vpdo 2023-07-09 Q27 — see the real figure at
corpus/reasoning-reference/vdo-vpdo-2023-07-09/page7.png:

    दोपहर के एक भोज में आलू व टमाटर दोनों परोसे गये। कुछ ने आलू व कुछ ने टमाटर
    लिया। वहाँ पर कुछ मांसाहारी थे जिन्होंने इनमें से कुछ भी नहीं लिया। बचे हुए
    लोगों ने आलू व टमाटर दोनों लिया।  -> (A), two overlapping circles plus a
    detached one.

VERIFIED before building: "some took only potato" and "some took only tomato"
force the two sets to OVERLAP without either containing the other; "some took
neither" forces a third set DISJOINT from both. Exactly one of the four
standard arrangements satisfies all three, which is what makes the question
answerable.

THE ONLY TYPE HERE THAT USES `option_images`. Each option is its own PNG, and
pipeline/build_paper.py:289-294 renders them inline beside (a)-(d) — that
branch SUPPRESSES text options entirely, so `options` must still be present but
is not shown. run_pipeline.validate counts `option_images` for the answer-letter
range check, so the two must be the same length.

HOW IT IS CORRECT BY CONSTRUCTION: a RELATION is chosen first (which sets
overlap, which contain, which are disjoint), the correct layout is derived from
it, and the three distractors are layouts of DIFFERENT relations. The
description is generated from the same relation, so picture and text cannot
disagree.

Interface:
    generate(rng)            -> question dict (with `_figure_options`)
    layout(relation)         -> list[dict]      # pure, for tests
"""
from __future__ import annotations

import random

# Relations, as (key, hindi description template, layout builder).
#
# Each layout is a list of circles in unit coordinates. The GEOMETRY encodes
# the relation — overlapping circles genuinely overlap, contained ones are
# genuinely inside — so a test can re-derive the relation from the layout and
# catch a mismatch between the picture and the words.
_RELATIONS = {
    # A and B overlap; C is separate from both.
    "overlap_plus_disjoint": [
        {"cx": 0.26, "cy": 0.50, "r": 0.19},
        {"cx": 0.50, "cy": 0.50, "r": 0.19},
        {"cx": 0.84, "cy": 0.50, "r": 0.13},
    ],
    # C contains B contains A — a strict chain.
    "nested": [
        {"cx": 0.50, "cy": 0.50, "r": 0.40},
        {"cx": 0.50, "cy": 0.50, "r": 0.26},
        {"cx": 0.50, "cy": 0.50, "r": 0.12},
    ],
    # All three mutually separate.
    "all_disjoint": [
        {"cx": 0.20, "cy": 0.50, "r": 0.16},
        {"cx": 0.54, "cy": 0.50, "r": 0.16},
        {"cx": 0.86, "cy": 0.50, "r": 0.12},
    ],
    # Two inside a third, and those two overlap each other.
    "two_inside_overlapping": [
        {"cx": 0.50, "cy": 0.50, "r": 0.42},
        {"cx": 0.40, "cy": 0.45, "r": 0.20},
        {"cx": 0.60, "cy": 0.45, "r": 0.20},
    ],
    # Two separate sets both inside a third.
    "two_inside_disjoint": [
        {"cx": 0.50, "cy": 0.50, "r": 0.42},
        {"cx": 0.35, "cy": 0.42, "r": 0.16},
        {"cx": 0.65, "cy": 0.58, "r": 0.16},
    ],
}

# (relation key, description) — the words a candidate reads. Written so that
# exactly one arrangement satisfies them, which is checked by the test that
# re-derives the relation from the geometry.
_DESCRIPTIONS = {
    "overlap_plus_disjoint": [
        ("भोज में {a} व {b} दोनों परोसे गये । कुछ लोगों ने केवल {a} लिया और "
         "कुछ ने केवल {b} । कुछ लोगों ने इनमें से कुछ भी नहीं लिया, और शेष "
         "लोगों ने {a} व {b} दोनों लिये ।"),
    ],
    "nested": [
        ("सभी {c} , {b} हैं । सभी {b} , {a} हैं ।"),
    ],
    "all_disjoint": [
        ("कोई {a} , {b} नहीं है । कोई {b} , {c} नहीं है । कोई {a} , {c} "
         "नहीं है ।"),
    ],
    "two_inside_overlapping": [
        ("सभी {b} और सभी {c} , {a} हैं । कुछ {b} , {c} भी हैं ।"),
    ],
    "two_inside_disjoint": [
        ("सभी {b} , {a} हैं । सभी {c} भी {a} हैं । परन्तु कोई {b} , {c} "
         "नहीं है ।"),
    ],
}

# Nouns for the three sets, in triples that read naturally together.
_NOUNS = [
    ("आलू", "टमाटर", "मांसाहारी"),
    ("शिक्षक", "लेखक", "किसान"),
    ("डॉक्टर", "अभियंता", "वकील"),
    ("क्रिकेट खिलाड़ी", "फुटबॉल खिलाड़ी", "तैराक"),
    ("गुलाब", "कमल", "पत्थर"),
    ("कवि", "गायक", "व्यापारी"),
]

_STEMS = [
    "नीचे दिये गये तार्किक चित्रों में से कौन-सा चित्र उपरोक्त परिस्थिति को "
    "सही से दर्शाता है ?",
    "उपर्युक्त कथनों को सबसे उपयुक्त रूप से कौन-सा आरेख निरूपित करता है ?",
]


def layout(relation: str) -> list[dict]:
    """The circle layout for a relation. O(1).

    Independent of generate() — the tests call this, re-derive the relation
    from the geometry, and assert it matches the key.
    """
    return [dict(c) for c in _RELATIONS[relation]]


def generate(rng: random.Random) -> dict:
    """One Venn/logic-diagram question. O(1).

    Emits FOUR figure specs, one per option. render.py turns them into
    `option_images`; build_paper then shows the diagrams instead of text
    options.
    """
    correct = rng.choice(list(_RELATIONS))
    others = [r for r in _RELATIONS if r != correct]
    rng.shuffle(others)
    wrong = others[:3]

    a, b, c = rng.choice(_NOUNS)
    desc = rng.choice(_DESCRIPTIONS[correct]).format(a=a, b=b, c=c)

    relations = [correct] + wrong
    rng.shuffle(relations)
    idx = relations.index(correct)

    return {
        "stem": desc + " " + rng.choice(_STEMS),
        # The text options are placeholders: build_paper.py:289-294 renders
        # option_images INSTEAD of these. They must still exist and match in
        # length, because run_pipeline.validate sizes the answer-letter range
        # from whichever is present and build_paper reads `options` in its
        # else-branch.
        "options": ["(चित्र A)", "(चित्र B)", "(चित्र C)", "(चित्र D)"],
        "answer": "abcd"[idx],
        "format": "plain",
        # Intrinsic: a nesting chain is read at a glance; telling two
        # inside-a-third arrangements apart needs care.
        "difficulty": ("easy" if correct in ("nested", "all_disjoint") else
                       "moderate"),
        "reason": (f"विवरण के अनुसार समुच्चयों का सम्बन्ध '{correct}' है; "
                   f"अतः विकल्प ({'abcd'[idx].upper()}) सही है।"),
        "_type": "venn",
        "_dedup_key": f"venn:{correct}:{a}",
        # FOUR specs, one per option — rendered into option_images.
        "_figure_options": [{"kind": "venn", "circles": layout(r)}
                            for r in relations],
    }
