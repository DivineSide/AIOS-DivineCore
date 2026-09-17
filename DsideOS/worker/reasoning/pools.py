# -*- coding: utf-8 -*-
"""pools — shared cosmetic vocabulary for the reasoning generators.

THE SPLIT THAT MATTERS: a reasoning question has SEMANTIC slots (the walk legs,
the cipher rule, the family shape) and COSMETIC slots (who is walking, which
verb, which unit). Changing a semantic slot changes the answer; changing a
cosmetic one changes nothing. Everything in this module is cosmetic, which is
why it can be varied freely without any risk to correctness.

The two axes multiply: ~40 names x 3 verbs x 4 closing phrasings on top of a
parameter space in the thousands means two papers essentially never look alike,
long before the numbers differ.

GENDER IS TRACKED because blood-relation questions need it — a tree node
labelled पुत्री must not be handed a masculine name. MALE and FEMALE are kept
as separate lists rather than one list with a flag, so a generator physically
cannot draw the wrong one.

Names and places are Uttarakhand-appropriate: these papers are written for
candidates in that state and the real PYQs use regional names (योगेश, कैलाश,
गोविन्द, हरिन्दर all appear in the 2023 papers).

Interface — all module-level constants, no functions. Import and pick with the
caller's own `rng` so one seed drives the whole question.
"""
from __future__ import annotations

# ── people ──────────────────────────────────────────────────────────────────
# Drawn from names that actually appear in UKSSSC papers plus common regional
# names. Kept to unambiguous single given names: a two-word name inside a
# nested possessive ("X की माता की पुत्री") reads badly.
MALE_NAMES = [
    "योगेश", "कैलाश", "गोविन्द", "हरिन्दर", "राजेश", "जितेन्द्र", "सुरेश",
    "महेश", "दिनेश", "मुकेश", "रमेश", "नरेश", "प्रकाश", "विकास", "आनन्द",
    "मोहन", "सोहन", "किशोर", "अनिल", "सुनील", "विनोद", "प्रमोद", "देवेन्द्र",
    "नरेन्द्र", "भुवन", "चन्दन", "पंकज", "मनोज", "अजय", "विजय",
]

FEMALE_NAMES = [
    "सीता", "गीता", "रीता", "अनीता", "सुनीता", "कविता", "ममता", "संगीता",
    "पूजा", "दीपा", "मीना", "बीना", "रेखा", "लता", "उमा", "शारदा",
    "कमला", "विमला", "सरला", "निर्मला", "राधा", "पुष्पा", "आशा", "उषा",
    "हेमा", "नीलम", "रजनी", "सपना", "ज्योति", "प्रियंका",
]

# ── places ──────────────────────────────────────────────────────────────────
# Real Uttarakhand towns, for linear-arrangement and direction questions that
# want named locations rather than bare letters. Short names only — a long one
# repeated four times in a stem crowds the line.
PLACES = [
    "देहरादून", "हरिद्वार", "ऋषिकेश", "नैनीताल", "अल्मोड़ा", "पिथौरागढ़",
    "चमोली", "रुद्रप्रयाग", "टिहरी", "उत्तरकाशी", "बागेश्वर", "चम्पावत",
    "कोटद्वार", "रानीखेत", "मसूरी", "काशीपुर", "रुद्रपुर", "हल्द्वानी",
]

# Neutral village labels, for when the question is about geometry rather than
# geography and real place names would imply real distances.
VILLAGE_LABELS = ["A", "B", "C", "D", "E", "P", "Q", "R", "S"]

# ── directions ──────────────────────────────────────────────────────────────
# (label, dx, dy) with +x = East, +y = North. The tuple IS the semantics — a
# generator must use these vectors, never re-derive them from the label.
DIRECTIONS = {
    "पूर्व":   (1, 0),
    "पश्चिम":  (-1, 0),
    "उत्तर":   (0, 1),
    "दक्षिण":  (0, -1),
}

# Turn vocabulary, for stems that phrase legs as turns rather than absolute
# directions. Cosmetic: the generator still computes with DIRECTIONS.
#
# GENDER-NEUTRAL ONLY. "मुड़ा और" was here until a smoke test produced
# "उषा ने ... मुड़ा और ... चली" — a masculine participle against a feminine
# subject. Conjunct participles (मुड़कर/घूमकर) do not inflect, so they are safe
# with any subject; anything that inflects belongs in a *_M / *_F pair instead.
TURN_WORDS = ["मुड़कर", "घूमकर"]

# ── units ───────────────────────────────────────────────────────────────────
# Both spellings appear in real papers ("2 km" and "5 किलोमीटर" in the same
# question on vdo-vpdo 2023-07-09 Q23). Pick ONE per question and use it for
# every distance in that question — mixing them inside one stem reads as an
# OCR artefact rather than a style choice.
DISTANCE_UNITS = ["किमी", "किलोमीटर", "km"]

# ── phrasings ───────────────────────────────────────────────────────────────
# Walk verbs. All intransitive past, all agree with a masculine singular
# subject — generators using a FEMALE name must use WALK_VERBS_F instead.
WALK_VERBS_M = ["चला", "गया", "चलकर पहुँचा"]
WALK_VERBS_F = ["चली", "गई", "चलकर पहुँची"]

# Closing questions for direction-and-distance. Each is a complete sentence.
DISTANCE_QUESTIONS = [
    "अपने प्रारम्भिक बिन्दु से वह कितनी दूर है ?",
    "प्रारम्भ बिन्दु से उसकी दूरी कितनी है ?",
    "वह अपने प्रारम्भिक स्थान से कितनी दूरी पर है ?",
]

# Openers for a blood-relation question. `{name}` is substituted.
RELATION_OPENERS = [
    "एक व्यक्ति का परिचय कराते हुए {name} ने कहा,",
    "एक तस्वीर की ओर इशारा करते हुए {name} ने कहा,",
    "{name} ने एक व्यक्ति की ओर संकेत करते हुए कहा,",
]

# Closing questions for blood relations.
RELATION_QUESTIONS = [
    "वह व्यक्ति {name} से किस प्रकार सम्बन्धित है ?",
    "उस व्यक्ति का {name} से क्या सम्बन्ध है ?",
]

# Series stems.
SERIES_QUESTIONS = [
    "निम्नलिखित श्रृंखला में प्रश्नवाचक चिह्न (?) के स्थान पर क्या आएगा ?",
    "निम्न श्रृंखला में लुप्त संख्या ज्ञात कीजिए :",
    "दी गई श्रृंखला को पूर्ण करने वाला विकल्प चुनिए :",
]

# Coding-decoding stems. `{src}`, `{code}`, `{dst}` are substituted.
CODING_QUESTIONS = [
    "यदि किसी कूट भाषा में '{src}' को '{code}' लिखा जाता है, "
    "तो उसी कूट भाषा में '{dst}' को क्या लिखा जाएगा ?",
    "एक कूट भाषा में '{src}' का कूट '{code}' है, तो '{dst}' का कूट क्या होगा ?",
]
