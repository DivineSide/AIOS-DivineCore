# -*- coding: utf-8 -*-
"""batch_gen — generate N questions per subject in ONE model call.

WHY (2026-09-11, round-2 rebuild): the old engine ran one model call per
question (`_gen_slot`), which meant (a) the same system prompt + passages were
re-sent per question, and (b) the model could not see its own other questions,
so duplicate entities were caught only AFTER the fact by PaperGuard's collision
re-queue. Batching fixes both at the source: shared context is sent once, and
cross-question awareness prevents duplication instead of detecting it.

SHAPE — one call per SUBJECT, one question per SECTION:

    ### विषय 1: <section name>
    <that section's passages>

    ### विषय 2: <section name>
    <that section's passages>
    ...

The model writes exactly ONE question per numbered section. One, not 2-3:
sections are the book's own authored headings and are already niche, so a
second question from the same section would restate the first.

Batching per SUBJECT (not per exam) is deliberate — subjects already run
concurrently, and a cross-subject batch would serialise them for a dedup
benefit that barely exists, since two subjects rarely share an entity.

OUTPUT is enforced by CONSTRAINED DECODING (response_format json_schema,
strict:true), not by prompt adherence: the sampler is masked per token so a
schema-violating token has zero probability. Verified live on gpt-oss-120b via
Groq (2026-09-06). This retires the hand-rolled `_parse_json_object` fence
stripping and most of validate_gen's structural checks. It does NOT make the
content true — that stays grounding's job (the same verified call returned
well-formed JSON claiming N.D. Tiwari was Uttarakhand's first CM).

Interface:
    build_batch_prompt(subject, subject_label, sections)
        -> (system, user, response_format)
    parse_batch(raw, sections) -> list[draft dict]

`sections` is [(section_name, [passage dicts]), ...] — the caller decides which
sections a paper draws from (rag sampling + reuse tracking, migration 007).
"""
from __future__ import annotations

import json
import re

# Sibling worker modules — batch_gen is imported with worker/ on
# sys.path (see generate.py), so these are flat imports like its own.
import difficulty
import formats

# One question per section. See module docstring.
QUESTIONS_PER_SECTION = 1

BATCH_SYSTEM = """# ROLE
You are an Indian competitive-exam question writer (UKSSSC-style), writing in
Hindi (Devanagari). English proper nouns and technical terms stay in English.

# WHAT YOU ARE MAKING
{n} numbered study sections follow, each on a different topic from {subject}.
Write EXACTLY ONE question per section, in order. Question K comes only from
section K.

# HOW TO BUILD ONE QUESTION — follow these five steps in order

STEP 1 — FIND THE FACT.
Read the section and pick ONE sentence that states something specific and
checkable: a name, a place, a year, a work, a scheme, a pairing. That sentence
is your question's foundation. If the section only mentions its topic in
passing and states no such sentence, pick the plainest fact it DOES state — a
simple question on a real fact beats a clever one on an invented fact.

STEP 2 — DECIDE WHAT THE STUDENT MUST KNOW.
Turn that fact into a question a candidate could answer while sitting in an
exam hall with no book in front of them. Write it as a fact about the world:
"चंद वंश की राजधानी किसने स्थानांतरित की?" — a standalone question. It must
still make sense to someone who has never seen your section, so everything
needed to answer it belongs inside the stem.

STEP 3 — BUILD THE DISTRACTORS FROM THE SAME FAMILY.
Name the category your answer belongs to — a dynasty, a district, a river, a
year, an organisation — then choose three more members of THAT SAME category.
Four options of one kind is what forces a candidate to actually know the
answer. If one option is a year and three are names, the year is visibly the
odd one and the question tests nothing.
Then check each distractor against your own stem and confirm it is genuinely
wrong. If a distractor could also be a correct answer, the question has two
right answers and is unusable — this happens most often when the stem asks
which item belongs to a set and the distractors are also in that set.

STEP 4 — PREFER A NAME OVER A NUMBER.
Ask WHO, WHICH, or WHAT — a person, place, organisation, book, scheme or term.
Real papers are ~90% text-answered. Years and quantities are easy to lift from
a passage, which is exactly why they are over-produced; use one only when the
date or figure IS the point of the fact.

STEP 5 — WRITE THE REASON AS THE BARE FACT.
`reason` is one sentence a teacher reads to see why the key is right. State the
fact and stop: "मेरठ की खड़ी बोली आदर्श और मानक मानी जाती है।"
The study section is your private working material — the student, and the
teacher reading this reason, never see it. So nothing you write may point back
at it: not "सामग्री के अनुसार", not "जैसा कि पाठ में कहा गया", not "सारणी 22.3
में", and not implicitly either ("सूची में सम्मिलित है", "उपर्युक्त में से").
If a fact came from a table, state the fact and never mention the table.

# ACROSS THE WHOLE BATCH
You can see all {n} of your questions at once — use that. Every question must
turn on a DIFFERENT fact and a DIFFERENT entity: if two would share a correct
answer, change one before you answer. Vary how the stems open; {n} questions
that all begin the same way read as machine-made.

# BEFORE YOU ANSWER
For each question, point to the sentence in ITS OWN section that makes the key
correct. If you cannot, go back to STEP 1 and pick a different fact from that
section rather than supplying one from your own knowledge — an unsupported
fact is the single most common way a question fails."""


# Per-format response shapes. Each mirrors EXACTLY what the matching
# formats.build_* expects, because one call handles one format (grouped by
# format precisely so a single strict schema can describe the whole batch — a
# schema cannot say "item 3 is a match and item 4 is plain").
#
# Only the FACTS are requested for non-plain formats, never the assembled
# question: formats.py computes the कूट grid and the answer letter, which is
# what makes a structurally inconsistent match/order question impossible rather
# than merely unlikely. See formats.py's module docstring.
_FORMAT_FIELDS: dict[str, dict] = {
    "plain": {
        "required": ["stem", "options", "answer_index"],
        "properties": {
            "stem": {"type": "string"},
            "options": {"type": "array", "minItems": 4, "maxItems": 4,
                        "items": {"type": "string"}},
            "answer_index": {"type": "integer", "minimum": 0, "maximum": 3},
        },
    },
    "match": {
        "required": ["stem_subject", "pairs"],
        "properties": {
            "stem_subject": {"type": "string"},
            "pairs": {"type": "array", "minItems": 4, "maxItems": 4,
                      "items": {"type": "array", "minItems": 2, "maxItems": 2,
                                "items": {"type": "string"}}},
        },
    },
    "statement": {
        "required": ["context", "statements", "correct_indexes"],
        "properties": {
            "context": {"type": "string"},
            "statements": {"type": "array", "minItems": 2, "maxItems": 3,
                           "items": {"type": "string"}},
            "correct_indexes": {"type": "array", "minItems": 1, "maxItems": 3,
                                "items": {"type": "integer",
                                          "minimum": 0, "maximum": 2}},
        },
    },
    "assertion": {
        "required": ["assertion", "reason_r", "relation"],
        "properties": {
            "assertion": {"type": "string"},
            # NOT "reason": the batch item already has a teacher-facing
            # `reason`, and formats.build_assertion's own `reason` is the R
            # STATEMENT. Renamed here and mapped back in parse_batch so the two
            # never collide.
            "reason_r": {"type": "string"},
            "relation": {"type": "string",
                         "enum": ["both-true-explains", "both-true-not-explains",
                                  "a-true-r-false", "a-false-r-true"]},
        },
    },
    "order": {
        "required": ["stem", "items"],
        "properties": {
            "stem": {"type": "string"},
            "items": {"type": "array", "minItems": 4, "maxItems": 4,
                      "items": {"type": "string"}},
        },
    },
}


def _schema(n: int, fmt: str = "plain") -> dict:
    """Strict JSON schema for a batch of n questions in ONE format.

    `strict: true` + `additionalProperties: false` gives constrained decoding —
    the model cannot emit a wrong shape. minItems == maxItems == n forces
    exactly one question per section, so a short batch is impossible by
    construction rather than something we detect afterwards.
    """
    spec = _FORMAT_FIELDS.get(fmt, _FORMAT_FIELDS["plain"])
    props = {
        "section_number": {"type": "integer", "minimum": 1, "maximum": n},
        # Echoing the assigned difficulty back is not decoration: an enum the
        # model must emit makes it commit to the level BEFORE writing the stem,
        # and gives a cheap post-hoc check that 50/30/20 actually landed.
        "difficulty": {"type": "string",
                       "enum": ["easy", "moderate", "hard"]},
        "reason": {"type": "string"},
        **spec["properties"],
    }
    return {
        "name": f"question_batch_{fmt}",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["questions"],
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": n,
                    "maxItems": n,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": (["section_number", "difficulty", "reason"]
                                     + spec["required"]),
                        "properties": props,
                    },
                }
            },
        },
    }


def build_batch_prompt(subject: str, subject_label: str,
                       sections: list[tuple[str, list[dict]]],
                       difficulties: list[str] | None = None,
                       fmt: str = "plain",
                       style_examples: list[str] | None = None,
                       ) -> tuple[str, str, dict]:
    """(system, user, response_format) for one subject's batch.

    sections: [(section_name, [passage dicts]), ...] — one entry per question to
    be written, in paper order. Each passage dict needs a "text" key.

    Complexity: O(total passage chars) — string assembly only, no I/O.
    Scale note: fine to ~40 sections. Beyond that the prompt gets long enough
    that per-question attention degrades; split into several batches instead.
    Tradeoff: one call per subject (not per exam) keeps subjects parallel and
    blast radius small, at the cost of no cross-SUBJECT dedup awareness — which
    is cheap to lose, since two subjects rarely share an answer entity.
    """
    n = len(sections)
    diffs = list(difficulties or ["moderate"] * n)
    diffs = (diffs + ["moderate"] * n)[:n]      # never misalign with sections

    blocks = []
    for i, (name, passages) in enumerate(sections, 1):
        body = "\n\n".join(p.get("text", "") for p in passages) or "(सामग्री उपलब्ध नहीं)"
        blocks.append(f"### विषय {i}: {name}   [कठिनाई: {diffs[i-1]}]\n{body}")
    user = (
        "━━━ अध्ययन सामग्री (आपके तथ्यों का एकमात्र स्रोत) ━━━\n\n"
        + "\n\n".join(blocks)
        + f"\n\n━━━\nअब {n} प्रश्न लिखिए — प्रत्येक विषय से ठीक एक, उसी क्रम में, "
        + "और प्रत्येक की दी गई कठिनाई पर।"
    )

    system = BATCH_SYSTEM.format(n=n, subject=subject_label or subject)

    # Per-subject difficulty steer. Only THIS subject's block is injected —
    # all seven would be ~7k wasted chars per call and would dilute the steer.
    system += "\n\n" + difficulty.block(subject)

    # Format contract, when this batch is not plain. One call per (subject,
    # format) means the whole batch shares one contract and one schema shape.
    if fmt != "plain" and fmt in formats.FORMATS:
        _label = formats.FORMATS[fmt]["label"]
        _contract = formats.FORMATS[fmt]["prompt"]
        system += (f"\n\n# FORMAT — {_label}\n"
                   f"Every question in this batch uses this format.\n"
                   f"{_contract}")

    # Real past questions from THIS exam+subject, for register only. Sampled
    # fresh per run so papers do not converge on one example's phrasing.
    if style_examples:
        system += ("\n\n# REAL PAST QUESTIONS — STYLE REFERENCE ONLY\n"
                   "Match their register, phrasing and length. Do NOT reuse "
                   "their topics or facts: your topic comes from the study "
                   "section you are given, never from these.\n\n"
                   + "\n\n".join(f"[{i}] {e}" for i, e in
                                  enumerate(style_examples, 1)))

    return system, user, {"type": "json_schema", "json_schema": _schema(n, fmt)}


# Attribution phrases the model appends to `reason` ("..., जैसा कि सामग्री में
# कहा गया है"). Measured 2026-09-11: gpt-oss-120b did this on 6/6 questions in
# the first batched run, so every question was dropped by validate_gen's
# material-reference gate despite the FACTS being correct and grounded.
#
# The prompt now forbids it explicitly (see BATCH_SYSTEM), but prompt adherence
# is exactly what cannot be relied on — it is the failure mode that killed
# sarvam-30b (86% of its drops). `reason` is teacher-facing prose, NOT
# load-bearing for correctness: the stem, options and answer carry the
# question, and grounding checks the FACT, not this sentence. So a trailing
# attribution clause is strippable, unlike a bad stem which must be rejected.
#
# Stems are deliberately NOT stripped: a stem that refers to the material is
# broken as a QUESTION (the student cannot see the text), so it must fail the
# gate and be regenerated, not silently patched.
_ATTRIB_RX = re.compile(
    r"\s*(?:,|।)?\s*(?:जैसा कि|जैसाकि)?\s*"
    r"(?:इस |उपर्युक्त |दी गई |दिए गए |प्रदत्त )?"
    r"(?:अध्ययन\s*)?(?:सामग्री|पाठ|पाठ्यांश|स्रोत|सारणी|तालिका|अनुच्छेद)"
    r"[^।।]*?(?:कहा गया है|बताया गया है|उल्लेख(?:ित)? है|के अनुसार|में दिया गया है)"
    r"\s*[।।.]?\s*$"
)


def strip_attribution(reason: str) -> str:
    """Remove a trailing source-attribution clause from a reason.

    Returns the bare fact. Idempotent, and a no-op when no clause is present.
    If stripping would empty the reason, the original is kept — an empty reason
    is worse than one that trips the gate, because the gate at least reports it.

    Complexity: O(len(reason)) — one anchored regex, no backtracking blowup
    (the inner class excludes the sentence terminator).
    """
    if not reason:
        return reason
    out = _ATTRIB_RX.sub("", reason).strip()
    if not out:
        return reason
    # Leading form: "सामग्री में बताया गया है कि <fact>" -> "<fact>"
    lead = re.match(
        r"^\s*(?:इस |उपर्युक्त |प्रदत्त )?(?:अध्ययन\s*)?"
        r"(?:सामग्री|पाठ|पाठ्यांश|स्रोत|सारणी\s*[\d.]*|तालिका\s*[\d.]*)"
        r"[^।।]*?(?:में )?(?:बताया गया है|कहा गया है|उल्लेख है|दिया गया है)"
        r"\s*कि\s*(.+)$", out)
    if lead and lead.group(1).strip():
        out = lead.group(1).strip()
    if out and out[-1] not in "।।.":
        out += "।"
    return out


def parse_batch(raw: str, sections: list[tuple[str, list[dict]]],
                fmt: str = "plain") -> list[dict]:
    """Raw model reply -> drafts, each tagged with its own section's passages.

    Constrained decoding guarantees the shape, so this does no fence stripping
    or brace slicing (unlike the old _parse_json_object). It DOES validate
    section_number: a schema can enforce the range 1..n, but not that each
    section appears exactly once.

    Returns drafts in section order. A section the model skipped is simply
    absent — the caller treats that as a drop rather than a crash. Attaching
    `_passages` per draft matters because grounding must check each question
    against ITS OWN section's material, never the whole batch's.

    Complexity: O(n). Raises json.JSONDecodeError only if the provider ignored
    the schema — worth letting it surface rather than silently returning [].
    """
    data = json.loads(raw)
    out: dict[int, dict] = {}
    for q in data.get("questions", []):
        k = q.get("section_number")
        if not isinstance(k, int) or not (1 <= k <= len(sections)):
            continue
        if k in out:                      # duplicate section_number: keep first
            continue
        name, passages = sections[k - 1]
        draft = {
            "reason": strip_attribution(q.get("reason", "")),
            "difficulty": q.get("difficulty", ""),
            "_section": name,
            "_passages": passages,
        }
        # Pass through exactly the fields THIS format's builder expects. The
        # schema already guaranteed they are present and well-shaped, so this
        # is a copy, not a validation.
        for key in _FORMAT_FIELDS.get(fmt, _FORMAT_FIELDS["plain"])["required"]:
            draft[key] = q.get(key)
        if fmt == "assertion":
            # build_assertion reads the R statement from "reason"; the batch
            # item's own "reason" is the teacher-facing explanation, so the
            # schema named the R statement "reason_r" to avoid the collision.
            # Map it back and move the teacher note to "why", which is what
            # build_assertion actually reads for it.
            draft["why"] = draft.pop("reason", "")
            draft["reason"] = draft.pop("reason_r", "")
        out[k] = draft
    return [out[k] for k in sorted(out)]
