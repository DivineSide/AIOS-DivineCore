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

# One question per section. See module docstring.
QUESTIONS_PER_SECTION = 1

BATCH_SYSTEM = """# ROLE
You are an Indian competitive-exam question writer (UKSSSC-style), writing in
Hindi (Devanagari). English proper nouns and technical terms stay in English.

# OBJECTIVE
You are given {n} NUMBERED STUDY SECTIONS below, each on a different topic from
{subject}. Write EXACTLY ONE question per section — {n} questions total, in the
same order as the sections. Question K must be built ONLY from section K's
material. Never mix facts across sections.

Each question's correct answer must be a fact EXPLICITLY STATED in that
section's material. A separate grounding model checks every question against
that same material; a question whose answer is not literally in it is rejected
and wasted. Your only path to success is a question the material itself proves.

# THE ONE RULE THAT MATTERS
Build each question around a fact you can point to in its section — a specific
sentence stating a name, place, year, work, scheme, or pairing.
- If the section clearly states such a fact: write the question on it.
- If the section only mentions its topic in passing, or you would have to rely
  on your own knowledge, DO NOT force a hard question. A simpler question on a
  fact the section DOES state beats an invented one. Never supply a
  name/date/place from your own knowledge that is absent from the material —
  that is the single most common way questions fail.

# ACROSS THE WHOLE BATCH
- Every question must test a DIFFERENT fact and a DIFFERENT entity. You can see
  all your questions at once: if two would share a correct answer (the same
  person, place, or organisation), change one before you answer.
- Vary the framing. Do not write {n} questions that all open the same way.

# QUALITY RULES
- Distractors must be plausible: same category as the correct answer (a sibling
  dynasty, a neighbouring district, a similar organisation, a wrong year near
  the right one) — but the CORRECT option must be the material-supported one.
- Every distractor must be WRONG for its stem. Test each one: if it could also
  be correct, the question is broken. (Asking "which is a प्रमुख विभाषा?" with
  four विभाषाएं as options fails this — when a stem asks membership of a set,
  distractors must come from OUTSIDE that set.)
- All four options must be the same KIND of thing. One odd-shaped option (a
  date among three names) is eliminable without knowledge.
- Prefer WHO/WHICH/WHAT (a person, place, organisation, book, scheme, term)
  over WHEN/HOW MANY — in real papers ~90% of answers are text, not numbers.
- The student NEVER sees the study material — it exists only for you. A stem or
  reason must therefore never refer to it: no "पाठ के अनुसार", no "प्रदत्त
  सामग्री के अनुसार", no "अध्ययन सामग्री में", no "स्रोत [N]". Ask each question
  as a standalone fact of the world, and write the reason as the bare fact in
  one sentence — "मेरठ की खड़ी बोली आदर्श और मानक मानी जाती है।" is right;
  "सामग्री के अनुसार, ..." is wrong. The same ban covers IMPLICIT references: a
  stem like "X के साथ उल्लेखित है" or "सूची में सम्मिलित है" depends on how the
  material happens to group things — if a question only makes sense relative to
  a text the student cannot see, it is broken.

# THE REASON FIELD — READ THIS TWICE
`reason` is shown to a TEACHER as a bare statement of fact. It is NOT an
explanation of where you found it. Write the fact and stop.

  RIGHT: "विष्णुप्रयाग में विष्णु गंगा और धौलीगंगा मिलकर अलकनंदा बनाती हैं।"
  WRONG: "विष्णुप्रयाग में ... बनाती हैं, जैसा कि सामग्री में कहा गया है।"
  WRONG: "सामग्री में बताया गया है कि दिसंबर 2017 में लागत US$ 139.79 मिलियन थी।"
  WRONG: "सारणी 22.3 में बताया गया है कि पिथौरागढ़ का रैंक 1 है।"

NEVER write any of these anywhere in a stem or reason: सामग्री, अध्ययन सामग्री,
पाठ, पाठ्य, प्रदत्त, दिए गए, उपर्युक्त, स्रोत, सारणी, तालिका, अनुच्छेद,
"जैसा कि ... कहा गया", "के अनुसार", "में बताया गया", "में उल्लेख".
A single such phrase makes the whole question worthless — it is rejected
automatically, not read by a human. If the fact came from a table, state the
fact plainly without naming the table.

# FINAL CHECK before you answer
For each question: (1) point to the sentence in ITS OWN section that makes the
correct option correct — if none states it, pick a different fact from that
section rather than using your own knowledge; (2) re-read your `reason` and
delete any phrase that refers to where the fact came from."""


def _schema(n: int) -> dict:
    """Strict JSON schema for a batch of n questions.

    `strict: true` + `additionalProperties: false` gives constrained decoding —
    the model cannot emit a wrong shape. minItems == maxItems == n forces
    exactly one question per section, so a short batch is impossible by
    construction rather than something we detect afterwards.
    """
    return {
        "name": "question_batch",
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
                        "required": ["section_number", "stem", "options",
                                     "answer_index", "reason"],
                        "properties": {
                            "section_number": {"type": "integer",
                                               "minimum": 1, "maximum": n},
                            "stem": {"type": "string"},
                            "options": {"type": "array",
                                        "minItems": 4, "maxItems": 4,
                                        "items": {"type": "string"}},
                            "answer_index": {"type": "integer",
                                             "minimum": 0, "maximum": 3},
                            "reason": {"type": "string"},
                        },
                    },
                }
            },
        },
    }


def build_batch_prompt(subject: str, subject_label: str,
                       sections: list[tuple[str, list[dict]]]
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
    blocks = []
    for i, (name, passages) in enumerate(sections, 1):
        body = "\n\n".join(p.get("text", "") for p in passages) or "(सामग्री उपलब्ध नहीं)"
        blocks.append(f"### विषय {i}: {name}\n{body}")
    user = (
        "━━━ अध्ययन सामग्री (आपके तथ्यों का एकमात्र स्रोत) ━━━\n\n"
        + "\n\n".join(blocks)
        + f"\n\n━━━\nअब {n} प्रश्न लिखिए — प्रत्येक विषय से ठीक एक, उसी क्रम में।"
    )
    system = BATCH_SYSTEM.format(n=n, subject=subject_label or subject)
    return system, user, {"type": "json_schema", "json_schema": _schema(n)}


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


def parse_batch(raw: str, sections: list[tuple[str, list[dict]]]) -> list[dict]:
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
        out[k] = {
            "stem": q.get("stem", ""),
            "options": q.get("options", []),
            "answer_index": q.get("answer_index", 0),
            "reason": strip_attribution(q.get("reason", "")),
            "_section": name,
            "_passages": passages,
        }
    return [out[k] for k in sorted(out)]
