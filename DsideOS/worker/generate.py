# -*- coding: utf-8 -*-
"""AI-generative question pipeline — subject + count -> N exam-grade questions.

REDESIGNED 2026-07-12 as a HARNESS (same philosophy that fixed extraction):
the model supplies knowledge, code builds structure, mechanical gates detect
failure, and an informed retry loop corrects it. Modules:

  blueprint.py     — the harness owns every count (format slots per paper,
                     subjects per exam) via largest-remainder allocation of
                     MEASURED distributions from real papers. No prose quotas.
  formats.py       — per-format contracts. For सुमेलित/कथन/A-R/क्रम the model
                     returns only facts (pairs, statements, order, relation);
                     code assembles the stem block, options and answer letter,
                     so structural inconsistency is impossible.
  validate_gen.py  — pure-code invariants (options, Hindi, year sanity) +
                     paper-level guards (stem dedup, entity-repeat).
  ground.py        — Haiku grounding gate: the claimed fact must be quotable
                     from the source passages, else the question is rejected.

Per-slot flow (ONE topic, ONE format, its own context — variety by structure):

    passages = passage_lookup(topic, subject)          # substance (multi-fact)
    examples = pyq_rag_lookup(topic, subject, format)  # style, format-true
    draft    = GEN_MODEL(contract, passages, examples) # knowledge only
    q        = formats.build(draft)                    # code assembles
    validate -> paper-guard -> ground                  # mechanical gates
    failure  -> retry with the SPECIFIC reason fed back (<=2), else drop the
                slot and top up from another topic. Deliverable stays clean;
                drops are reported in gen-meta for the dashboard.

Modes:
    generate_questions(subject, count) -> (questions, meta)   # Phase A (live)
    generate_exam(exam, total)         -> (questions, meta)   # Phase B —
        per-exam quotas get locked WITH THE CLIENT; blueprint's measured
        SUBJECT_MIX is the opening proposal.

Topic sourcing differs by mode (2026-07-18, syllabus.py):
    subject mode — no exam context exists, so topics are inferred from a
        random PYQ sample (what the exam family actually tests, in aggregate).
    exam mode    — the OFFICIAL syllabus (syllabus.py, transcribed from the
        commission's advertisement PDFs) seeds the topics; PYQs then only
        supply per-topic style examples. A syllabus topic with zero PYQ
        coverage still generates (style prompt degrades gracefully) — this is
        how a fresh syllabus revision gets covered before any past paper
        tests it, and it decouples topic VARIETY from PYQ-pool size.
"""
import asyncio
import json
import logging
import os
import random
import sys
import zlib
from pathlib import Path

logger = logging.getLogger(__name__)

import anthropic

REPO_ROOT = Path(__file__).resolve().parents[2]
RAG = REPO_ROOT / "clients" / "target-academy" / "rag"
# Our own folder too: Celery imports this as worker.generate (package mode), so
# `import blueprint` needs worker/ on sys.path explicitly — running generate.py
# as a script from its own directory hides this, package mode does not.
WORKER_DIR = Path(__file__).resolve().parent
for _p in (str(WORKER_DIR), str(RAG)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import query as rag  # noqa: E402

import blueprint  # noqa: E402
import formats  # noqa: E402
import ground  # noqa: E402
import syllabus  # noqa: E402
from validate_gen import PaperGuard, validate_question  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
# Drafting is the intelligence step — worth the smart tier. Output is small
# (facts only, code builds the rest), so cost stays ~$1 per 100-question paper.
GEN_MODEL = os.environ.get("GEN_MODEL", SONNET)

GEN_PROVIDER = os.environ.get("GEN_PROVIDER", "anthropic").lower()
# Tried sarvam-30b (2026-07-22): ~9x faster per raw draft call than 105b, but
# a real 50Q pipeline test showed it ignores SLOT_SYSTEM's "never reference
# the study material in the reason text" rule far more often than 105b does
# (~86% of all drops were this one instruction-following miss, not real
# grounding failures) — the retry churn from that made the NET paper slower
# than 105b despite the faster raw calls (32/50 questions in 26.9 min).
# Reverted to 105b; reasoning_effort stays disabled below regardless of
# model (see _sarvam_reasoning_effort) since that part of the speedup is
# real and doesn't carry this tradeoff. Revisit 30b if the prompt gets
# tightened enough to close the instruction-following gap.
SARVAM_MODEL = os.environ.get("SARVAM_MODEL", "sarvam-105b")
SARVAM_BASE_URL = "https://api.sarvam.ai/v1"

TOPICS_DIVISOR = 2       # ~count/2 distinct topics (was 4 — variety collapsed)
TOPICS_CAP = 40
PYQ_SEED_K = 40          # random PYQs fed to topic extraction
BOOK_TOP_K = 4           # passages per slot
PYQ_TOP_K = 2            # style examples per slot
PASSAGE_THRESHOLD = 0.20
PYQ_THRESHOLD = 0.10

TOPIC_DEDUP_THRESHOLD = 0.78   # cosine sim above this = treat as duplicate
                               # enough to refetch. MEASURED, not guessed
                               # (2026-07-25): real same-fact rephrasings
                               # ("गढ़वाली बोली की उत्पत्ति" vs "...किस भाषा का
                               # रूप") score 0.81 and 0.80; a genuinely
                               # DIFFERENT topic in the same domain ("पंवार
                               # वंश के शासक" vs "चंद वंश के शासक" — two
                               # different dynasties) scores 0.73 — these
                               # ranges OVERLAP, so no threshold perfectly
                               # separates "same fact reworded" from
                               # "related but distinct fact" on short topic
                               # phrases with this embedding model. Goal is
                               # NOT zero topic overlap (real exams legitimately
                               # cluster several questions per broad theme) —
                               # it's minimizing exact-same-fact collisions.
                               # A false-positive refetch just produces
                               # another valid topic (cheap); a false
                               # negative reproduces today's Q77/Q82-style
                               # contradiction (expensive) — asymmetric cost
                               # justifies erring aggressive over conservative.
TOPIC_DEDUP_MAX_REFETCH = 3    # refetch attempts per colliding topic before
                               # accepting the closest candidate and moving on

MAX_SLOT_ATTEMPTS = 3    # 1 draft + up to 2 informed retries per slot
IN_FORMAT_TOPUP_RETRIES = 2   # a dropped rare-format slot gets this many
                              # top-up attempts in its OWN format before
                              # falling back to plain (see generate_questions'
                              # top-up loop) — counts against the topup
                              # circuit-breaker same as any other attempt,
                              # just doesn't give up on the pre-planned
                              # format immediately
# The paper's requested count is a PROMISE, not a target: a grounding
# rejection is a legitimate reason to drop ONE question, never a reason to
# under-deliver the PAPER. MAX_TOPUP used to be a flat 8 regardless of paper
# size — fine for a 10-question test, but mathematically guaranteed to fall
# short on a 100-question paper the moment more than 8 slots failed (observed
# live: job dd0ccd49fa354c3f, 44 real drops, delivered 81/100 because topup's
# budget ran out at 8, not because the harness couldn't recover more with
# fresh topics/passages). Fix: topup now keeps retrying — new topic, fresh
# RAG context each attempt — until the paper reaches its exact requested
# count. TOPUP_CIRCUIT_BREAKER exists ONLY to stop a truly pathological case
# (e.g. a subject with zero usable passages at all, where no number of
# retries could ever succeed) from looping forever; it's sized as a large
# multiple of the paper's own count so it should never trigger in practice —
# if it does, that's a real corpus/retrieval problem worth surfacing, not
# something to silently paper over by shipping short.
TOPUP_CIRCUIT_BREAKER_MULTIPLE = 5   # give up only after 5x the paper's own
                                     # question count in topup attempts
# Slots are independent network-bound work; only the PaperGuard is
# cross-question. Waves of K slots run fully parallel, then commit through the
# guard sequentially at the wave boundary — a collision (two slots landing the
# same answer entity) fails the later one, which re-runs next wave WITH the
# collision reason (informed, not blind). K=6 ≈ 6x wall-clock with zero gate
# skipped; above ~8 you brush API rate limits for marginal gain.
GEN_CONCURRENCY = max(1, int(os.environ.get("GEN_CONCURRENCY", "6")))

VALID_ANSWERS = {"a", "b", "c", "d"}

SUBJECT_LABELS = {
    "uk-history":          "उत्तराखंड का इतिहास",
    "uk-geography":        "उत्तराखंड का भूगोल",
    "uk-culture":          "उत्तराखंड की संस्कृति",
    "uk-general-studies":  "उत्तराखंड सामान्य अध्ययन",
    "general-gk":          "सामान्य ज्ञान",
    "hindi":               "सामान्य हिंदी",
    "computer":            "कंप्यूटर",
}

# Per-slot system prompt. Lean by design: the format CONTRACT carries the
# structural rules, the passages carry the facts, the examples carry the style
# — prose only states what code cannot enforce.
SLOT_SYSTEM = """# ROLE
You are an Indian competitive-exam question writer (UKSSSC-style), writing in
Hindi (Devanagari). English proper nouns and technical terms stay in English.

# OBJECTIVE
Write ONE question of the format: {format_label} — topic: "{topic}" (subject:
{subject}) — whose correct answer is a fact EXPLICITLY STATED in the STUDY
MATERIAL below. Every question you write is checked by a separate grounding
model against that same material; a question whose answer is not literally in
the material is rejected and wasted. So your only path to success is a question
the material itself proves.

# THE ONE RULE THAT MATTERS
Build the question around a fact you can point to in the study material — a
specific sentence stating a name, place, year, work, scheme, or pairing.
- If the material clearly states such a fact: write the question on it.
- If the material only mentions the topic in passing, or you'd have to rely on
  your own knowledge to answer, DO NOT force a question. It is better to write
  a simpler question on a fact the material DOES state than to invent one it
  doesn't. Never supply a name/date/place from your own knowledge that is
  absent from the material — that is the single most common way questions fail.

# QUALITY RULES
- Distractors must be plausible: same category as the correct answer (a sibling
  dynasty, a neighbouring district, a similar organisation, a wrong year near
  the right one) — but the CORRECT option must be the material-supported one.
- Every distractor must be WRONG for this stem. Before finalising, test each
  distractor against the question: if it could also be a correct answer, the
  question is broken. (Asking "which is a प्रमुख विभाषा?" with four विभाषाएं
  as options fails this — when the stem asks membership of a set, distractors
  must come from OUTSIDE that set.)
- Prefer WHO/WHICH/WHAT (a person, place, organisation, book, scheme, term)
  over WHEN/HOW MANY — in real papers ~90% of answers are text, not numbers.
- Mirror the framing and register of the REAL PAST QUESTIONS shown.
- The student NEVER sees the study material — it exists only for you. The stem
  and the reason must therefore never refer to it: no "पाठ के अनुसार", no
  "प्रदत्त सामग्री के अनुसार", no "अध्ययन सामग्री में", no "स्रोत [N]". Ask the
  question as a standalone fact of the world, and write the reason as the bare
  fact in one sentence — "मेरठ की खड़ी बोली आदर्श और मानक मानी जाती है।" is
  right; "सामग्री के अनुसार, ..." is wrong. The same ban covers IMPLICIT
  references: a stem like "X के साथ उल्लेखित है" or "सूची में सम्मिलित है"
  depends on how the material happens to group things — if the question only
  makes sense relative to a text the student cannot see, it is broken.

# OUTPUT
Return ONLY this JSON object (no prose, no fences):
{contract}

━━━ REAL PAST QUESTIONS (style reference only — NOT a source of facts) ━━━
{examples}

━━━ STUDY MATERIAL (your ONLY source of facts) ━━━
{passages}

━━━ FINAL CHECK before you answer ━━━
Point to the sentence in the STUDY MATERIAL above that makes your correct
option correct. If no sentence states it, choose a different fact from the
material — do NOT fall back on your own knowledge."""

_RETRY_USER = """Your previous attempt was rejected. Problem: {reason}

Write a corrected question now — same topic, same format, same JSON shape.
Fix the specific problem; use ONLY facts from the study material."""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


_sarvam = None


def _sarvam_client():
    global _sarvam
    if _sarvam is None:
        from openai import OpenAI
        key = os.environ.get("SARVAM_API_KEY", "")
        if not key:
            raise RuntimeError("SARVAM_API_KEY not set (required for GEN_PROVIDER=sarvam).")
        _sarvam = OpenAI(base_url=SARVAM_BASE_URL, api_key=key)
    return _sarvam


# ── model calls ──────────────────────────────────────────────────────────────

def _draft_anthropic(system: str, messages: list[dict]) -> str:
    msg = _client().messages.create(
        model=GEN_MODEL,
        max_tokens=1500,
        system=[{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    u = msg.usage
    logger.info("DRAFT model=%s | in=%d cache_r=%d cache_w=%d out=%d",
                GEN_MODEL, u.input_tokens,
                getattr(u, "cache_read_input_tokens", 0) or 0,
                getattr(u, "cache_creation_input_tokens", 0) or 0,
                u.output_tokens)
    return msg.content[0].text.strip() if msg.content else ""


def _sarvam_reasoning_effort() -> str | None:
    """None fully disables sarvam's hidden reasoning phase (Sarvam's own docs:
    "use None to completely disable reasoning when you want the fastest
    possible responses" — a distinct, lower state than the string "low", not
    just the bottom of the low/medium/high enum). This task (one short MCQ,
    facts-only, structural JSON) has no need for multi-step reasoning — the
    "thinking" was pure overhead, and per Sarvam's docs a too-small token
    budget for reasoning is exactly what caused the empty-content bug below,
    not a fluke of this codebase. SARVAM_REASONING env can still force a
    level ("low"/"medium"/"high") for comparison, but the default is now off.
    NOTE: must be Python None / JSON null, not the string "none" — Sarvam's
    API expects the enum values or a null, not a fourth string value."""
    val = os.environ.get("SARVAM_REASONING", "").strip().lower()
    return val if val in ("low", "medium", "high") else None


def _draft_sarvam(system: str, messages: list[dict]) -> str:
    # max_tokens: starter tier hard-caps at 4096; run just under it. With
    # reasoning disabled (see _sarvam_reasoning_effort) the old "reasoning ate
    # the whole budget, content came back empty" failure mode shouldn't recur,
    # but the warning below stays as a canary in case it does.
    resp = _sarvam_client().chat.completions.create(
        model=SARVAM_MODEL, max_tokens=4000,
        extra_body={"reasoning_effort": _sarvam_reasoning_effort()},
        messages=[{"role": "system", "content": system}] + messages,
    )
    choice = resp.choices[0]
    out = (choice.message.content or "").strip()
    if not out:
        logger.warning("SARVAM empty content (finish=%s, completion_toks=%s)",
                       choice.finish_reason,
                       getattr(resp.usage, "completion_tokens", "?"))
    return out


def _draft(system: str, messages: list[dict]) -> str:
    if GEN_PROVIDER == "sarvam":
        return _draft_sarvam(system, messages)
    return _draft_anthropic(system, messages)


def _complete(prompt: str, max_tokens: int = 1024) -> str:
    """Single-user-turn completion (no passages/system contract) for small
    helper tasks like topic extraction — routes through GEN_PROVIDER like
    _draft() does, instead of being hardcoded to one provider regardless of
    what's actually configured/funded. Previously _extract_topics() called
    anthropic.Anthropic() directly no matter what GEN_PROVIDER was set to;
    on a server with GEN_PROVIDER=sarvam and no ANTHROPIC_API_KEY (today's
    actual deployment), that call was GUARANTEED to fail every time it
    triggered — confirmed live via a real credit-exhaustion 400. Fails soft
    to "" on any error, same as before; callers already handle empty output
    by falling back to a subject-label topic."""
    if GEN_PROVIDER == "sarvam":
        resp = _sarvam_client().chat.completions.create(
            model=SARVAM_MODEL, max_tokens=max_tokens,
            extra_body={"reasoning_effort": _sarvam_reasoning_effort()},
            messages=[{"role": "user", "content": prompt}],
        )
        return (resp.choices[0].message.content or "").strip()
    msg = _client().messages.create(
        model=HAIKU, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip() if msg.content else ""


def _parse_json_object(text: str) -> dict | None:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        return None
    span = t[start:end + 1]
    for candidate in (span,
                      # models that echo template-escaped braces ({{...}}) —
                      # observed with sarvam-105b copying the contract literally
                      span.replace("{{", "{").replace("}}", "}")):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


# ── Phase 1 — subject -> topics ──────────────────────────────────────────────

def _parse_json_array(text: str) -> list:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip()
    start, end = t.find("["), t.rfind("]")
    if start != -1 and end > start:
        t = t[start:end + 1]
    try:
        data = json.loads(t)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def _dedupe_topics(topics: list[str], subject: str, exam: str | None,
                         official_pool: list[str]) -> list[str]:
    """Retrieval-first topic dedup: embed every topic BEFORE any generation
    slot is built, and replace any pair that's semantically the same
    underlying topic (not just a different string) — e.g. "गढ़वाली बोली की
    उत्पत्ति" and "गढ़वाली भाषा किस भाषा से" share zero substrings but ask the
    exact same fact. Keyword/stem comparison (what PaperGuard does post-hoc,
    on generated QUESTIONS) can't catch this; only embedding similarity on
    the TOPIC strings, done before generation starts, catches it up front —
    so two slots never even get assigned to write about the same fact,
    rather than catching it after two drafts already burned model calls.

    Official-syllabus topics get a replacement resampled from the unused
    remainder of the same official list (still authoritative, still
    official-only). LLM-inferred topics get re-prompted for one fresh
    replacement, explicitly excluding every topic already accepted.
    TOPIC_DEDUP_MAX_REFETCH caps retries per collision; if still colliding
    after that, the closest-to-unique candidate is accepted and logged
    loudly — this must never silently block or shrink the paper, same
    philosophy as the topup circuit breaker."""
    if len(topics) < 2:
        return topics

    embeds = await asyncio.gather(*[
        asyncio.to_thread(rag._embed, t) for t in topics
    ])
    accepted: list[str] = []
    accepted_embeds: list[list[float]] = []
    unused_official = [t for t in official_pool if t not in topics]

    for topic, emb in zip(topics, embeds):
        candidate, cand_emb = topic, emb
        for attempt in range(TOPIC_DEDUP_MAX_REFETCH + 1):
            sims = [_cosine(cand_emb, e) for e in accepted_embeds]
            worst = max(sims) if sims else 0.0
            if worst < TOPIC_DEDUP_THRESHOLD:
                break
            if attempt == TOPIC_DEDUP_MAX_REFETCH:
                logger.warning(
                    "topic-dedup[%s/%s]: '%s' still collides (sim=%.2f) after "
                    "%d refetches — accepting anyway, not blocking the paper",
                    subject, exam, candidate, worst, TOPIC_DEDUP_MAX_REFETCH)
                break
            if unused_official:
                candidate = unused_official.pop(random.randrange(len(unused_official)))
            else:
                exclude = ", ".join(f'"{t}"' for t in accepted + [candidate])
                prompt = (
                    f"Give ONE distinct exam topic/concept for the subject "
                    f"'{subject}', in Hindi (Devanagari). It must be "
                    f"COMPLETELY DIFFERENT from all of these already-used "
                    f"topics: {exclude}. Return ONLY the topic string, no "
                    f"prose, no JSON, no quotes."
                )
                try:
                    candidate = _complete(prompt, max_tokens=64).strip().strip('"')
                except Exception as e:
                    logger.warning("topic-dedup refetch failed (%s) — keeping "
                                   "prior candidate", e)
                    break
            if not candidate:
                break
            cand_emb = await asyncio.to_thread(rag._embed, candidate)
        accepted.append(candidate)
        accepted_embeds.append(cand_emb)
    return accepted


async def _extract_topics(subject: str, count: int,
                          exam: str | None = None) -> list[str]:
    """Derive distinct exam topics for `count` questions.

    Exam mode (exam on the master syllabus): the OFFICIAL taxonomy seeds the
    list — variety comes from the commission's own syllabus, not from
    whatever a 40-row PYQ sample happens to contain. Shortfall (official
    list smaller than n_topics) tops up from PYQ inference below.

    Subject mode (exam=None): PYQ-sample inference, unchanged — with no exam
    anchor there is no single official syllabus to consult."""
    n_topics = max(1, min(count // TOPICS_DIVISOR, TOPICS_CAP))

    official = syllabus.topics_for(subject, exam)
    if official:
        if len(official) >= n_topics:
            picked = random.sample(official, n_topics)
            picked = await _dedupe_topics(picked, subject, exam, official)
            logger.info("topics[%s/%s]: %d/%d from official syllabus",
                        subject, exam, len(picked), n_topics)
            return picked
        # official list exhausted — keep ALL of it, top up from PYQ inference
        n_topics -= len(official)
        logger.info("topics[%s/%s]: all %d official + %d PYQ-inferred",
                    subject, exam, len(official), n_topics)
    else:
        official = []

    seed_pyqs = await rag.pyq_lookup(subject, top_k=PYQ_SEED_K, exam=exam)
    if not seed_pyqs:
        return official or [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]

    examples = "\n".join(f"- {p['text'][:300]}" for p in seed_pyqs)
    prompt = (
        f"These are real exam questions for the subject '{subject}':\n\n{examples}\n\n"
        f"What distinct topics/concepts do these exam questions test? "
        f"Return exactly {n_topics} topic strings as a JSON array of strings, "
        f"no prose. Write each topic in Hindi (Devanagari script). "
        f"CRITICAL: every topic must be COMPLETELY DIFFERENT — no two topics should "
        f"overlap or be rewordings of each other. Cover as wide a range as possible."
    )
    try:
        raw = _complete(prompt, max_tokens=1024)
    except Exception as e:
        logger.warning("topic extraction failed (%s) — using subject label", e)
        raw = ""
    topics = [t for t in _parse_json_array(raw) if isinstance(t, str) and t.strip()]
    if not topics:
        return official or [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]
    combined = official + topics[:n_topics]
    return await _dedupe_topics(combined, subject, exam, official)


# ── the slot engine ──────────────────────────────────────────────────────────

async def _slot_context(subject: str, topic: str, fmt: str,
                        top_k: int = BOOK_TOP_K,
                        query_extra: str = "",
                        exam: str | None = None) -> tuple[list, str, str]:
    """Retrieve one slot's context. Returns (passages, passages_txt, examples_txt).

    `top_k`/`query_extra` support agentic RE-RETRIEVAL: when a draft is rejected
    by the grounding gate ("fact not in passages"), the caller re-invokes this
    with a WIDER top_k and the rejected question's own terms appended to the
    query — so the retry sees MORE and DIFFERENT passages instead of being handed
    the same thin material that produced the ungrounded question. Retrying with
    new evidence beats shipping a doubtful fact.

    `exam` (exam mode only) restricts PYQ style examples to THIS exam's own
    real papers — a vdo-vpdo slot must not imitate group-c's or driver's
    format mix. The any-subject-same-format fallback below intentionally
    KEEPS the exam filter (a rare format's shape still needs to come from
    this exam's own papers, just a different subject within it); only the
    final no-exam-context fallback drops it, and only because at that point
    no example beats a wrong-exam example less than no example at all — see
    the unfiltered call below."""
    search_topic = f"{topic} {query_extra}".strip() if query_extra else topic
    passages = await rag.passage_lookup(search_topic, subject=subject,
                                        top_k=top_k, threshold=PASSAGE_THRESHOLD)
    if not passages:
        # topic string too narrow — fall back to the subject's canonical label
        passages = await rag.passage_lookup(SUBJECT_LABELS.get(subject, subject),
                                            subject=subject, top_k=BOOK_TOP_K,
                                            threshold=0.10)
    examples = await rag.pyq_rag_lookup(topic, subject, top_k=PYQ_TOP_K,
                                        threshold=PYQ_THRESHOLD, format=fmt,
                                        exam=exam)
    if not examples and fmt != "plain":
        # rare format with no nearby example of that format — any-subject example
        # of the SAME FORMAT still teaches the shape better than nothing
        examples = await rag.pyq_rag_lookup(formats.FORMATS[fmt]["label"], subject,
                                            top_k=PYQ_TOP_K, threshold=0.0, format=fmt,
                                            exam=exam)
    if not examples:
        # last resort: drop the exam filter too (no format-true example exists
        # anywhere in this exam's own corpus) — any real PYQ of this subject
        # still teaches better than the placeholder text in etxt below
        examples = await rag.pyq_rag_lookup(topic, subject, top_k=PYQ_TOP_K,
                                            threshold=PYQ_THRESHOLD)

    ptxt = "\n\n".join(f"[{i + 1}] (book: {p.get('book', '')})\n{p.get('text', '')}"
                       for i, p in enumerate(passages)) or "(no material found)"
    etxt = "\n\n".join(f"[{i + 1}] {e.get('text', '')}"
                       for i, e in enumerate(examples)) or \
           "(no example available — use standard UKSSSC framing)"
    return passages, ptxt, etxt


def _seed(*parts) -> int:
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))


def _rejected_terms(draft: dict | None, topic: str) -> str:
    """Pull the entity the rejected draft was ASKING about, to steer the wider
    re-retrieval toward passages that actually contain it. We use the stem +
    the claimed-correct option — that's the fact that failed grounding, so the
    new search should hunt specifically for material stating it."""
    if not isinstance(draft, dict):
        return ""
    parts = []
    stem = draft.get("stem") or draft.get("question") or ""
    if isinstance(stem, str):
        parts.append(stem)
    # the claimed answer text (draft shapes vary: "answer" letter + options, or
    # an explicit answer string) — include whatever names the target fact
    opts = draft.get("options")
    ans = draft.get("answer")
    if isinstance(opts, list) and isinstance(ans, str) and len(ans) == 1:
        idx = "abcd".find(ans.lower())
        if 0 <= idx < len(opts):
            parts.append(str(opts[idx]))
    elif isinstance(ans, str):
        parts.append(ans)
    text = " ".join(parts).strip()
    return text[:200]   # keep the augmentation bounded


async def _gen_slot(subject: str, topic: str, fmt: str, slot_id: int,
                    guard: PaperGuard, slot_sem: asyncio.Semaphore,
                    initial_reason: str = "",
                    exam: str | None = None) -> tuple[dict | None, str]:
    """Generate one question — thin wrapper enforcing the GLOBAL concurrency
    cap via `slot_sem` before doing any real work. Every caller (waves in
    generate_questions, its top-up loop, across every subject a concurrent
    generate_exam() is running) shares the SAME semaphore instance, so total
    in-flight API calls never exceeds GEN_CONCURRENCY no matter how many
    subjects/waves are active at once.

    `slot_sem` is created fresh per top-level call (generate_exam /
    generate_questions — the two functions each Celery task wraps in its own
    asyncio.run()) and passed down, rather than cached as a module global.
    A semaphore is bound to the event loop that created it; asyncio.run()
    makes a NEW loop per job, so a global would occasionally survive a prior
    job's crash/timeout still locked and bound to that job's now-dead loop —
    the next job on the same worker process would then fail immediately with
    "bound to a different event loop" (observed 2026-07-22, job
    6c9771500e9a47ce, right after a prior job hit its Celery soft time
    limit mid-run). Scoping the semaphore to the call, not the process,
    makes that impossible — nothing outlives the job that created it."""
    async with slot_sem:
        return await _gen_slot_inner(subject, topic, fmt, slot_id, guard, initial_reason, exam)


async def _gen_slot_inner(subject: str, topic: str, fmt: str, slot_id: int,
                          guard: PaperGuard, initial_reason: str = "",
                          exam: str | None = None) -> tuple[dict | None, str]:
    """Generate one question. Returns (question, "") or (None, last_reason).
    `initial_reason` injects feedback from a wave-boundary collision so the
    re-run is informed, not a blind re-roll."""
    passages, ptxt, etxt = await _slot_context(subject, topic, fmt, exam=exam)
    if not passages:
        return None, f"no study material for topic '{topic}'"

    system = SLOT_SYSTEM.format(
        format_label=formats.FORMATS[fmt]["label"], topic=topic,
        subject=SUBJECT_LABELS.get(subject, subject),
        contract=formats.FORMATS[fmt]["prompt"],
        examples=etxt, passages=ptxt,
    )
    first_user = f"Write the question now. Format: {fmt}. JSON only."
    if initial_reason:
        first_user += (f"\nNOTE: a previous attempt was rejected — {initial_reason}. "
                       f"Avoid that problem.")
    messages = [{"role": "user", "content": first_user}]
    reason = ""
    grounding_failed = False   # set when the last rejection was the grounding gate
    for attempt in range(MAX_SLOT_ATTEMPTS):
        try:
            raw = await asyncio.to_thread(_draft, system, messages)
        except Exception as e:
            logger.warning("SLOT %s/%s draft failed: %s", topic, fmt, e)
            return None, f"model call failed: {e}"
        draft = _parse_json_object(raw)
        grounding_failed = False
        if draft is None:
            reason = "reply was not a single valid JSON object"
            # log the actual shape so provider quirks (reasoning preambles,
            # fences, truncation) are diagnosable from the worker log alone
            logger.warning("SLOT unparseable reply len=%d head=%r tail=%r",
                           len(raw), raw[:300], raw[-120:] if len(raw) > 300 else "")
        else:
            try:
                q = formats.build(fmt, draft, seed=_seed(subject, topic, slot_id, attempt))
                reason = validate_question(q) or guard.check(q) or ""
                if not reason:
                    ok, greason = await asyncio.to_thread(ground.check, q, passages)
                    if ok:
                        logger.info("SLOT ok topic=%r fmt=%s attempt=%d", topic, fmt, attempt + 1)
                        return q, ""
                    reason = greason
                    grounding_failed = True   # the fact wasn't in these passages
            except formats.FormatError as e:
                reason = str(e)
        logger.info("SLOT retry topic=%r fmt=%s attempt=%d reason=%s",
                    topic, fmt, attempt + 1, reason)

        # AGENTIC RE-RETRIEVAL: a grounding failure means the passages didn't
        # contain the fact — re-drafting against the SAME passages just invites
        # the same hallucination. Instead, fetch WIDER + DIFFERENT passages
        # (bigger top_k, query augmented by the rejected question's own terms)
        # and rebuild the prompt so the retry reasons over fresh evidence. This
        # is the "retry rather than ship a doubtful fact" loop. Parse/format
        # failures are the model's fault, not the material's — those keep the
        # same passages and just get the reason fed back (rewrite, below).
        if grounding_failed and attempt + 1 < MAX_SLOT_ATTEMPTS:
            wider = BOOK_TOP_K + 3 * (attempt + 1)   # 7, then 10, ...
            q_terms = _rejected_terms(draft, topic)
            new_passages, new_ptxt, new_etxt = await _slot_context(
                subject, topic, fmt, top_k=wider, query_extra=q_terms, exam=exam)
            if new_passages:
                passages, ptxt, etxt = new_passages, new_ptxt, new_etxt
                system = SLOT_SYSTEM.format(
                    format_label=formats.FORMATS[fmt]["label"], topic=topic,
                    subject=SUBJECT_LABELS.get(subject, subject),
                    contract=formats.FORMATS[fmt]["prompt"],
                    examples=etxt, passages=ptxt,
                )
                logger.info("SLOT re-retrieved topic=%r wider_k=%d (grounding miss)",
                            topic, wider)
                # fresh evidence -> a clean draft prompt, not a rewrite of the
                # rejected attempt (which was anchored to the old passages)
                messages = [{"role": "user", "content":
                             f"Write the question now. Format: {fmt}. JSON only. "
                             f"Base it ONLY on a fact explicitly stated in the "
                             f"study material above."}]
                continue

        # INFORMED retry (rewrite): the failure reason goes back to the model verbatim.
        messages = messages[:1] + [
            {"role": "assistant", "content": raw[:2000]},
            {"role": "user", "content": _RETRY_USER.format(reason=reason)},
        ]
    return None, reason


# ── orchestrators ────────────────────────────────────────────────────────────

async def generate_questions(subject: str, count: int,
                             exam: str | None = None,
                             slot_sem: asyncio.Semaphore | None = None,
                             fmt_counts: dict[str, int] | None = None,
                             ) -> tuple[list[dict], dict]:
    """Subject mode (exam=None) or one subject of an exam paper (exam set —
    official-syllabus topic seeding kicks in). Returns (questions, meta) —
    meta carries drop notes for the dashboard; the questions list is always
    clean (no flags).

    `slot_sem` caps total concurrent _gen_slot calls at GEN_CONCURRENCY (see
    _gen_slot's docstring for why this must be created fresh per job, not
    cached as a module global). Callers running multiple subjects concurrently
    (generate_exam) must create ONE semaphore and pass it to every subject's
    call, so the cap is shared across subjects, not per-subject. Subject-mode
    callers (this function invoked directly, its own top-level asyncio.run)
    leave it unset and get one scoped to just this call.

    `fmt_counts` (exam mode only): the pre-decided {format: count} for THIS
    subject, computed once for the whole paper by blueprint.exam_format_plan
    before any subject starts generating (see generate_exam) — real
    per-subject historical format proportions, not one ratio flattened
    across every subject. Subject-mode callers leave this unset and fall
    back to the global format_mix(), unchanged from before this parameter
    existed."""
    if slot_sem is None:
        slot_sem = asyncio.Semaphore(GEN_CONCURRENCY)
    topics = await _extract_topics(subject, count, exam=exam)
    if fmt_counts is None:
        fmt_counts = blueprint.allocate(count, blueprint.format_mix())
    # slot list: rare formats first so they land on distinct early topics
    slots = [f for f in ("match", "statement", "assertion", "order")
             for _ in range(fmt_counts.get(f, 0))]
    slots += ["plain"] * fmt_counts.get("plain", 0)

    guard = PaperGuard(total=count)
    out: list[dict] = []
    drops: list[dict] = []

    # WAVE CONCURRENCY: run GEN_CONCURRENCY slots in parallel, then commit their
    # results through the shared PaperGuard sequentially. Every gate still runs;
    # a wave-boundary collision (two parallel slots landing the same answer
    # entity — rare, since each slot has its own topic) re-queues the later slot
    # ONCE with the collision reason injected (informed re-run), then drops.
    pending: list[tuple[int, str, str, str]] = [
        (i, topics[i % len(topics)], fmt, "") for i, fmt in enumerate(slots)
    ]
    while pending:
        wave, pending = pending[:GEN_CONCURRENCY], pending[GEN_CONCURRENCY:]
        results = await asyncio.gather(*[
            _gen_slot(subject, topic, fmt, sid, guard, slot_sem,
                     initial_reason=reason, exam=exam)
            for sid, topic, fmt, reason in wave
        ])
        for (sid, topic, fmt, was_requeued), (q, reason) in zip(wave, results):
            if q is None:
                drops.append({"topic": topic, "format": fmt, "reason": reason})
                continue
            collision = guard.check(q)
            if collision is None:
                guard.commit(q)
                out.append(q)
            elif not was_requeued:
                logger.info("WAVE collision slot=%d: %s — informed re-run", sid, collision)
                pending.append((sid, topic, fmt, collision))
            else:
                drops.append({"topic": topic, "format": fmt,
                              "reason": f"wave collision persisted: {collision}"})

    # top-up: recover the count on fresh topics (same waves) — UNCAPPED except
    # for a circuit breaker (see TOPUP_CIRCUIT_BREAKER_MULTIPLE's docstring):
    # the requested count is a promise, not a target. A fixed topup budget
    # (the old MAX_TOPUP=8) is mathematically guaranteed to under-deliver the
    # moment a paper has more real failures than that budget — observed live
    # on a 100-question paper with 44 drops, capped at recovering only 8,
    # shipping 81/100. Each dropped slot gets up to IN_FORMAT_TOPUP_RETRIES
    # attempts IN ITS OWN ORIGINAL FORMAT before falling back to plain — a
    # paper pre-planned (via blueprint.exam_format_plan) for N match questions
    # must not have every failed match slot silently become plain; that would
    # throw away the whole point of the per-subject-per-format plan through
    # the exact mechanism it was built to fix. `drops` already carries each
    # failure's original `format`, so this is a queue of (format,
    # retries_left) rather than a single hardcoded "plain".
    topup_queue: list[tuple[str, int]] = [
        (d["format"], IN_FORMAT_TOPUP_RETRIES if d["format"] != "plain" else 0)
        for d in drops
    ]
    topup_ceiling = max(count * TOPUP_CIRCUIT_BREAKER_MULTIPLE, 20)
    topup = 0
    while len(out) < count and topup < topup_ceiling:
        need = min(count - len(out), GEN_CONCURRENCY, topup_ceiling - topup)
        batch = []
        for j in range(need):
            if topup_queue:
                fmt, retries_left = topup_queue.pop(0)
            else:
                fmt, retries_left = "plain", 0
            sid = 1000 + topup + j
            topic = topics[(len(slots) + topup + j) % len(topics)]
            batch.append((sid, topic, fmt, retries_left))
        results = await asyncio.gather(*[
            _gen_slot(subject, topic, fmt, sid, guard, slot_sem, exam=exam)
            for sid, topic, fmt, _ in batch
        ])
        for (sid, topic, fmt, retries_left), (q, reason) in zip(batch, results):
            if q is not None and guard.check(q) is None and len(out) < count:
                guard.commit(q)
                out.append(q)
            elif q is None:
                if retries_left > 0:
                    # re-queue in the SAME format, one fewer retry left —
                    # still counts against the circuit breaker overall, just
                    # doesn't give up on the original format immediately
                    topup_queue.append((fmt, retries_left - 1))
                else:
                    drops.append({"topic": topic, "format": f"{fmt}(topup)",
                                 "reason": reason})
        topup += need

    for i, q in enumerate(out, 1):
        q["n"] = i
        q.pop("_claim", None)

    meta = {
        "requested": count,
        "generated": len(out),
        "format_plan": fmt_counts,
        "format_actual": {f: sum(1 for q in out if q.get("format") == f)
                          for f in set(q.get("format", "plain") for q in out)},
        "drops": drops,
        "circuit_breaker_tripped": len(out) < count,
    }
    if len(out) < count:
        # This should be RARE — it means topup_ceiling (5x the paper's own
        # count) was exhausted without reaching the requested total, which
        # only happens if a subject/format combo is structurally unable to
        # ground ANY question (e.g. a corpus with real retrieval hits but no
        # single quotable fact for that topic — see ground.py). Surfaced
        # loudly, not silently absorbed, since the requested count is a
        # promise: this is a real corpus/retrieval gap worth investigating,
        # not an expected outcome.
        logger.error("generate: CIRCUIT BREAKER TRIPPED — only %d/%d for '%s' "
                    "after %d topup attempts (%d drops) — paper is short; "
                    "this subject/format likely has a real grounding gap",
                    len(out), count, subject, topup, len(drops))
    return out, meta


async def generate_exam(exam: str, total: int) -> tuple[list[dict], dict]:
    """Exam mode. Harness owns the counts (blueprint SUBJECT_MIX — measured
    opening proposal, client-lockable); the OFFICIAL syllabus owns the topic
    taxonomy (syllabus.py, per-subject seeding inside generate_questions).
    Per-exam SUBJECT_MIX numbers remain the client-session deliverable.

    Subjects run CONCURRENTLY, not one after another: each subject gets its
    own PaperGuard (created fresh inside generate_questions), so there is no
    shared state a race could corrupt — a sequential for-loop here was only
    ever adding wall-clock time, not correctness. Measured: a 10-question
    exam paper (7 subjects, ~1-3 questions each) took ~10 minutes serial;
    each subject barely used the wave concurrency inside generate_questions
    because 1-3 slots rarely fills a GEN_CONCURRENCY=6 wave anyway — the
    real waste was subjects waiting on each other, not slots within a
    subject waiting on each other.

    One semaphore is created HERE and shared across every subject's
    generate_questions() call, so the GEN_CONCURRENCY cap applies to the
    whole paper at once, not per-subject (see generate_questions'/_gen_slot's
    docstrings) — and because it's scoped to this single call (this function
    is exactly what each Celery task wraps in its own asyncio.run()), it can
    never survive into a later job's event loop.

    Format variety is ALSO pre-decided here, once, before any subject starts
    generating: blueprint.exam_format_plan() measures each subject's REAL
    historical format mix from pyq_chunks (not one ratio flattened across
    every subject — see blueprint.py's per-subject-format-planning section)
    and hands each subject's generate_questions() call its own fmt_counts.
    Uses rag._db() (query.py's thread-local psycopg2 connection, already
    timeout-bounded) via asyncio.to_thread since this is a sync DB call in
    an async function; any failure here is caught inside exam_format_plan
    itself and degrades to today's global-format_mix-per-subject behavior,
    so a planning-query hiccup never blocks the job."""
    per_subject = blueprint.allocate(total, blueprint.subject_mix(exam))
    subjects = [(subject, n) for subject, n in per_subject.items() if n > 0]
    fmt_plan = await asyncio.to_thread(
        blueprint.exam_format_plan, exam, dict(subjects), rag._db())
    slot_sem = asyncio.Semaphore(GEN_CONCURRENCY)
    results = await asyncio.gather(*[
        generate_questions(subject, n, exam=exam, slot_sem=slot_sem,
                          fmt_counts=fmt_plan[subject])
        for subject, n in subjects
    ])

    out: list[dict] = []
    metas: dict[str, dict] = {}
    for (subject, _), (qs, meta) in zip(subjects, results):
        for q in qs:
            q["subject"] = subject
        out.extend(qs)
        metas[subject] = meta
    for i, q in enumerate(out, 1):
        q["n"] = i
    return out, {"exam": exam, "per_subject_plan": per_subject,
                 "format_plan": fmt_plan, "subjects": metas}
