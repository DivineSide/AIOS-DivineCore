# -*- coding: utf-8 -*-
"""difficulty — per-subject definitions and exemplars of easy/moderate/hard.

WHY THIS IS PROMPT-TAUGHT, NOT RETRIEVED (2026-09-12): no PYQ in the corpus
carries a difficulty label, and difficulty is not one thing across subjects —
in general-gk it is how obscure the fact is, in hindi grammar it is whether the
rule has edge cases, in uk-history it is whether the figure is famous or the
answer needs sequencing. That is a DEFINITION to teach, not examples to fetch.

Difficulty is also INDEPENDENT OF FORMAT (see blueprint.DIFFICULTY_MIX): a
plain question can be hard, a match can be easy. Tying them together would cap
hard at the ~13% of the paper that is non-plain, and the target is 20%.

Only the CURRENT SUBJECT's block is injected into a prompt — dumping all seven
would be ~2k wasted tokens per call and would dilute the steer.

Interface:
    block(subject) -> str     # ready to paste into a system prompt
"""
from __future__ import annotations

# Per subject: (what makes a question easy / moderate / hard, then one worked
# exemplar per level). Exemplars are deliberately the SAME format (plain) at
# all three levels, so the model reads them as difficulty differences and not
# as format differences.
_SUBJECTS: dict[str, dict] = {
    "uk-history": {
        "easy": "a headline fact every candidate has seen — the founder of a "
                "major dynasty, the year Uttarakhand was formed, the name of a "
                "famous movement",
        "moderate": "a real but second-tier fact — a specific ruler's capital, "
                    "the leader of a named movement, a treaty's other party",
        "hard": "a lesser-known figure, a precise sequence of events, or a "
                "fact that requires knowing WHICH of two similar things is "
                "meant (two dynasties with overlapping territory, two revolts "
                "in the same decade)",
        "ex_easy": "उत्तराखण्ड राज्य की स्थापना किस वर्ष हुई? → 2000",
        "ex_moderate": "चंद वंश की राजधानी चम्पावत से अल्मोड़ा किसने स्थानांतरित की? "
                       "→ कल्याण चंद",
        "ex_hard": "कुमाऊँ परिषद् के प्रथम अधिवेशन (1917, अल्मोड़ा) की अध्यक्षता "
                   "किसने की? → जयदत्त जोशी",
    },
    "uk-geography": {
        "easy": "a well-known physical feature — the highest peak, the main "
                "river, the state capital's district",
        "moderate": "a specific named feature among several of its kind — which "
                    "district a particular glacier or lake sits in",
        "hard": "a precise classification or a less-famous feature — which "
                "category a lake belongs to, which tributary joins where, a "
                "pass most candidates cannot place",
        "ex_easy": "उत्तराखण्ड की सबसे ऊँची चोटी कौन-सी है? → नंदा देवी",
        "ex_moderate": "गोविन्द पशु विहार राष्ट्रीय उद्यान किस जनपद में स्थित है? "
                       "→ उत्तरकाशी",
        "ex_hard": "नैनीताल और भीमताल किस प्रकार की झीलों के उदाहरण हैं? "
                   "→ टेक्टॉनिक (भ्रंशन) झीलें",
    },
    "uk-culture": {
        "easy": "a famous festival, dance or pilgrimage every candidate knows",
        "moderate": "a specific instrument, garment or ritual tied to a named "
                    "region or community",
        "hard": "a niche local practice, a folk form's regional variant, or an "
                "author/work pairing outside the standard list",
        "ex_easy": "उत्तराखण्ड का राज्य वृक्ष कौन-सा है? → बुरांश",
        "ex_moderate": "मुख्य रूप से 'मशकबीन' का प्रयोग किस नृत्यशैली में किया जाता "
                       "है? → छोलिया",
        "ex_hard": "रामायण का गढ़वाली अनुवाद, जिसे 'गढ़ भाषा लीला रामायण' कहा जाता "
                   "है, किसने किया? → गुमानी पंत",
    },
    "uk-general-studies": {
        "easy": "a basic fact of state governance — who heads a body, what a "
                "well-known scheme is for",
        "moderate": "a specific provision, year of an act, or the department "
                    "owning a named programme",
        "hard": "an exact statutory detail — the composition of an authority, a "
                "threshold figure, or which act supersedes which",
        "ex_easy": "उत्तराखण्ड का राज्य पशु कौन-सा है? → कस्तूरी मृग",
        "ex_moderate": "उत्तराखण्ड पुलिस अधिनियम किस वर्ष अधिनियमित किया गया? → 2007",
        "ex_hard": "उत्तराखण्ड पुलिस अधिनियम, 2007 के अनुसार राज्य पुलिस शिकायत "
                   "प्राधिकरण की संरचना क्या है? → अध्यक्ष सहित पाँच सदस्य",
    },
    "hindi": {
        "easy": "a textbook rule with an unambiguous answer — a common संधि, a "
                "well-known पर्यायवाची, a standard मुहावरा",
        "moderate": "a rule applied to a less common word, or a distinction "
                    "between two similar forms (तत्सम vs तद्भव)",
        "hard": "an edge case of a rule, an irregular form, or a word whose "
                "correct वर्तनी/लिंग most candidates get wrong",
        "ex_easy": "'विद्यालय' में कौन-सी संधि है? → दीर्घ संधि",
        "ex_moderate": "'पुष्कर' किस शब्द का पर्यायवाची है? → तालाब",
        "ex_hard": "'वनौषधि' में कौन-सी संधि है? → गुण संधि",
    },
    "general-gk": {
        "easy": "a fact from general awareness — a national symbol, a famous "
                "first, a capital city",
        "moderate": "a specific constitutional article, a scheme's launch year, "
                    "a named commission's recommendation",
        "hard": "a precise article number, an obscure organisation, or a fact "
                "requiring you to distinguish between two similar provisions",
        "ex_easy": "भारत का पहला समाचार पत्र कौन-सा था? → बंगाल गजट",
        "ex_moderate": "'द्वैध शासन की समाप्ति' की सिफारिश किस आयोग ने की? "
                       "→ साइमन कमीशन",
        "ex_hard": "भारतीय संविधान का अनुच्छेद 233 किसकी नियुक्ति से संबंधित है? "
                   "→ जिला न्यायाधीश",
    },
    "computer": {
        "easy": "a basic definition — what a device does, what an acronym "
                "expands to",
        "moderate": "a specific capability or a distinction between two similar "
                    "technologies",
        "hard": "a precise technical detail — a valid address range, a protocol "
                "port, which layer a function belongs to",
        "ex_easy": "कंप्यूटर का मस्तिष्क किसे कहा जाता है? → CPU",
        "ex_moderate": "निम्न में से कौन-सा ऑपरेटिंग सिस्टम का कार्य नहीं है? "
                       "→ वेब ब्राउज़िंग",
        "ex_hard": "निम्नलिखित में से कौन-सा वैध IPv4 पता है? → 172.16.254.1",
    },
}

_FALLBACK = {
    "easy": "a fact most prepared candidates will know",
    "moderate": "a specific fact requiring real preparation",
    "hard": "a niche fact or one needing careful distinction",
    "ex_easy": "", "ex_moderate": "", "ex_hard": "",
}


# The Indian-discipline subjects are CARVED OUT of general-gk (same authored
# bullets, regrouped so a teacher can order one discipline — see
# taxonomy_data/indian-*.json). They share general-gk's difficulty character
# exactly: what makes a polity question hard is still "a precise article number
# vs. two similar provisions". Aliasing keeps the worked exemplars, which is
# what actually makes the model hit a level; the generic _FALLBACK has none.
_ALIASES = {
    "indian-history": "general-gk",
    "indian-geography": "general-gk",
    "indian-polity": "general-gk",
    "indian-economics": "general-gk",
}


def block(subject: str) -> str:
    """The difficulty section of a system prompt, for ONE subject.

    Returns "" for an unknown subject rather than raising — a missing steer is
    better than a failed generation. Complexity: O(1), pure string building.
    """
    d = _SUBJECTS.get(_ALIASES.get(subject, subject))
    if d is None:
        d = _FALLBACK
        if not d["ex_easy"]:
            return ("# DIFFICULTY\nEach question below is tagged easy, moderate "
                    "or hard. Easy = " + d["easy"] + ". Moderate = "
                    + d["moderate"] + ". Hard = " + d["hard"] + ".\n")
    ex = ""
    if d["ex_easy"]:
        ex = ("\nExamples of each level in THIS subject (these show DIFFICULTY "
              "only — write your own question in the format you are told, on "
              "the topic you are given):\n"
              f"  EASY     — {d['ex_easy']}\n"
              f"  MODERATE — {d['ex_moderate']}\n"
              f"  HARD     — {d['ex_hard']}\n")
    return (
        "# DIFFICULTY\n"
        "Each numbered section below carries a difficulty. Hit it deliberately —\n"
        "a paper where everything is the same difficulty is useless for ranking\n"
        "candidates. Difficulty is about the FACT you choose and how the stem is\n"
        "framed, NOT about the question's format.\n\n"
        f"In {subject}:\n"
        f"  EASY     = {d['easy']}\n"
        f"  MODERATE = {d['moderate']}\n"
        f"  HARD     = {d['hard']}\n"
        f"{ex}"
    )
