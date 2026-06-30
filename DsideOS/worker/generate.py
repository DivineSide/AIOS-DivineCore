# -*- coding: utf-8 -*-
"""AI-generative question pipeline — subject + count -> N exam questions.

Four phases:

  1. PYQ topic extraction (Haiku)  — sample real past questions for the subject,
     ask Haiku what concepts they test -> a short list of topic strings.
     PYQs serve dual purpose: topic signal (what this exam tests) + style signal
     (how questions are framed). Haiku extracts topics FROM the PYQs, so the
     topics always reflect real exam patterns for this subject.

  2. Topic -> per-topic buckets (RAG) — for each topic, fetch its own dedicated
     book chunks (facts) and PYQ examples (style). Returns a dict keyed by topic.
     Keeping material per-topic is the structural guarantee of variety: Phase 3
     generates questions for one topic at a time using ONLY that topic's context,
     so the model can never drift into a neighbouring topic mid-batch.

  3. Generate questions (per topic, isolated context) — iterate over topics,
     each gets its own scoped model call with only its chunks + PYQ examples.
     N questions are distributed across topics (count // n_topics per topic,
     remainder distributed to first topics). A top-up loop catches any shortfall
     from validation drops.

  4. Build — handled by the caller (generate_task).

This module only owns phases 1-3 and exposes one coroutine:

    questions = await generate_questions(subject, count)
    # -> list[dict] each matching the Question schema (n, stem, options, answer, ...)
"""
import asyncio
import json
import logging
import math
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

import anthropic

REPO_ROOT = Path(__file__).resolve().parents[2]
RAG = REPO_ROOT / "clients" / "target-academy" / "rag"
if str(RAG) not in sys.path:
    sys.path.insert(0, str(RAG))

import query as rag  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
GEN_MODEL = HAIKU  # Anthropic model used when GEN_PROVIDER=anthropic

GEN_PROVIDER = os.environ.get("GEN_PROVIDER", "anthropic").lower()
SARVAM_MODEL = os.environ.get("SARVAM_MODEL", "sarvam-105b")
SARVAM_BASE_URL = "https://api.sarvam.ai/v1"

# RAG depth per topic. Each topic gets its own dedicated context — these are
# per-topic limits, not total limits. With topic isolation, BOOK_TOP_K=4 means
# each topic's call sees exactly 4 book passages and 2 PYQ examples.
TOPICS_DIVISOR = 2       # aim for ~count/2 distinct topics (2 questions per topic)
PYQ_SEED_K = 40          # random PYQs fed to Haiku for topic extraction
BOOK_TOP_K = 4           # book passages per topic
PYQ_TOP_K = 2            # PYQ style examples per topic
BOOK_THRESHOLD = 0.20
BOOK_FALLBACK_THRESHOLD = 0.15
PYQ_THRESHOLD = 0.20

# Output token budget per model call. With topic isolation each call is small:
# 4 book chunks + 2 PYQ examples + N questions (N = count // n_topics, usually 2).
# Sarvam-105b reasons; reasoning tokens eat into MAX_OUTPUT_TOKENS. At 2q/call
# the output is tiny (~540 tokens) so even with 1000 reasoning tokens we're safe
# under 4096. Override via env for paid tier.
if GEN_PROVIDER == "sarvam":
    MAX_OUTPUT_TOKENS = int(os.environ.get("SARVAM_MAX_TOKENS", "8192"))
    MAX_QUESTIONS_PER_CALL = int(os.environ.get("SARVAM_BATCH", "4"))
else:
    MAX_OUTPUT_TOKENS = 8192
    MAX_QUESTIONS_PER_CALL = 25

VALID_ANSWERS = {"a", "b", "c", "d"}

SUBJECT_LABELS = {
    "uk-history":          "उत्तराखंड का इतिहास",
    "uk-geography":        "उत्तराखंड का भूगोल",
    "uk-culture":          "उत्तराखंड की संस्कृति",
    "uk-general-studies":  "उत्तराखंड सामान्य अध्ययन",
    "general-gk":          "सामान्य ज्ञान",
    "hindi":               "सामान्य हिंदी",
}

# Per-topic system prompt. Each call is scoped to ONE topic — the model only
# sees chunks and PYQ examples for that topic, so it can't drift elsewhere.
GEN_SYSTEM = """You are an Indian competitive-exam question writer for UKSSSC, UPPSC, and similar
state PSC papers.

You are generating questions for the topic: "{topic}" (subject: {subject}).

You have been given:
1. REAL PAST EXAM QUESTIONS (PYQ EXAMPLES) — study these carefully. Mirror their:
   - Question framing and sentence structure
   - Hindi register and formality level
   - Option length and distractor style
   - Difficulty level and concept depth
2. STUDY MATERIAL — factual book excerpts about this topic. Every question you
   generate must be answerable from this material. Do not invent facts.

RULES:
- Language: Hindi (Devanagari). English proper nouns stay in English.
- Each question: exactly 4 options (a), (b), (c), (d)
- Difficulty: vary between easy, medium, and hard
- Each question must test a DIFFERENT specific fact — different date, person,
  place, event, or number. Never ask about the same entity twice.
- Distractors must be plausible — not obviously wrong
- For numerical/reasoning questions: include a worked solution in "solution" field

OUTPUT: Return ONLY a valid JSON array, no prose, no markdown fences:
[
  {{
    "n": 1,
    "stem": "question text in Hindi",
    "options": ["option a text", "option b text", "option c text", "option d text"],
    "answer": "a",
    "reason": "≤160 chars justification"
  }}
]

━━━ PYQ EXAMPLES (style reference) ━━━
{pyq_examples}

━━━ STUDY MATERIAL (factual source for this topic only) ━━━
{book_chunks}"""


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


# ── Phase 1 — subject -> topics (Haiku) ──────────────────────────────────────

async def _extract_topics(subject: str, count: int) -> list[str]:
    """Use Sarvam to derive N/TOPICS_DIVISOR distinct exam topics for the subject.
    Sarvam owns all Hindi generation — topic strings are Hindi and feed directly
    into the RAG query and the Phase 3 system prompt, so clean Hindi here matters.
    Seeds Sarvam with a random PYQ sample for topic signal."""
    n_topics = max(1, count // TOPICS_DIVISOR)

    seed_pyqs = await rag.pyq_lookup(subject, top_k=PYQ_SEED_K)
    if not seed_pyqs:
        return [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]

    examples = "\n".join(f"- {p['text'][:300]}" for p in seed_pyqs)
    prompt = (
        f"These are real exam questions for the subject '{subject}':\n\n{examples}\n\n"
        f"What distinct topics/concepts do these exam questions test? "
        f"Return exactly {n_topics} topic strings as a JSON array of strings, "
        f"no prose. Write each topic in Hindi (Devanagari script). "
        f"CRITICAL: every topic must be COMPLETELY DIFFERENT — no two topics should "
        f"overlap or be rewordings of each other. Cover as wide a range as possible. "
        f"Example: [\"उत्तराखंड का गठन\", \"गढ़वाल राज्य का इतिहास\"]"
    )
    if GEN_PROVIDER == "sarvam":
        raw = _gen_batch_sarvam("You are a helpful assistant.", prompt, n_topics)
    else:
        msg = _client().messages.create(
            model=HAIKU,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip() if msg.content else ""
    topics = _parse_json_array(raw)
    topics = [t for t in topics if isinstance(t, str) and t.strip()]
    if not topics:
        return [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]
    return topics[:n_topics]


# ── Phase 2 — topics -> per-topic buckets (RAG, no LLM) ──────────────────────

async def _collect_material(topics: list[str], subject: str) -> dict[str, dict]:
    """For each topic, fetch its own dedicated book chunks and PYQ style examples
    in parallel. Returns a dict keyed by topic:
        {topic: {"book_chunks": [...], "pyq_examples": [...]}}

    Each topic's bucket is self-contained — Phase 3 generates questions for one
    topic at a time using ONLY that bucket, which is the structural guarantee
    that questions from different topics never share context."""
    book_results, pyq_results = await asyncio.gather(
        asyncio.gather(*(
            rag.rag_lookup(stem=t, top_k=BOOK_TOP_K, threshold=BOOK_THRESHOLD, subject=subject)
            for t in topics
        )),
        asyncio.gather(*(
            rag.pyq_rag_lookup(topic=t, subject=subject, top_k=PYQ_TOP_K, threshold=PYQ_THRESHOLD)
            for t in topics
        )),
    )

    fallback_topic = SUBJECT_LABELS.get(subject, subject.replace("-", " "))
    buckets: dict[str, dict] = {}

    for topic, book_passages, pyq_passages in zip(topics, book_results, pyq_results):
        if not book_passages:
            # Topic string was too abstract or wrong language — fall back to
            # the subject's canonical Hindi label for the embedding lookup.
            book_passages = await rag.rag_lookup(
                stem=fallback_topic, top_k=BOOK_TOP_K,
                threshold=BOOK_FALLBACK_THRESHOLD, subject=subject,
            )
        buckets[topic] = {
            "book_chunks": book_passages[:BOOK_TOP_K],
            "pyq_examples": pyq_passages[:PYQ_TOP_K],
        }
        logger.info(
            "BUCKET topic=%r | book_chunks=%d pyq_examples=%d",
            topic, len(buckets[topic]["book_chunks"]), len(buckets[topic]["pyq_examples"]),
        )

    return buckets


# ── Phase 3 — per-topic isolated generation ───────────────────────────────────

def _gen_questions(subject: str, count: int,
                   buckets: dict[str, dict]) -> list[dict]:
    """Iterate over topics. Each topic gets its own model call with ONLY its
    own book chunks and PYQ examples. Questions per topic are distributed evenly
    (remainder goes to first topics). A global top-up loop recovers any shortfall
    from validation drops without re-using a topic that already yielded enough."""
    topics = list(buckets.keys())
    n_topics = len(topics)

    # Distribute questions evenly across topics. E.g. count=10, n_topics=5 -> 2 each.
    # count=11, n_topics=5 -> [3,2,2,2,2]. Each topic is responsible for its quota.
    base = count // n_topics
    remainder = count % n_topics
    quota = [base + (1 if i < remainder else 0) for i in range(n_topics)]

    out: list[dict] = []
    seen_stems: set[str] = set()

    def _accept(batch_qs: list[dict], src_books: list[str]) -> int:
        accepted = 0
        for q in batch_qs:
            if not isinstance(q, dict) or not q.get("stem"):
                continue
            opts = q.get("options")
            if not isinstance(opts, list) or len(opts) != 4:
                continue
            ans = str(q.get("answer", "")).strip().lower()
            if ans not in VALID_ANSWERS:
                continue
            norm = " ".join(str(q["stem"]).split()).lower()
            if norm in seen_stems:
                continue
            seen_stems.add(norm)
            q["answer"] = ans
            if src_books and not q.get("sources"):
                q["sources"] = src_books
            out.append(q)
            accepted += 1
        return accepted

    for i, (topic, q) in enumerate(zip(topics, quota)):
        if q == 0:
            continue
        bucket = buckets[topic]
        book_chunks = bucket["book_chunks"]
        pyq_examples = bucket["pyq_examples"]

        if not book_chunks:
            logger.warning("SKIP topic=%r — no book chunks", topic)
            continue

        src_books = sorted({c.get("book", "") for c in book_chunks if c.get("book")})
        book_material = "\n\n".join(
            f"[{j+1}] (book: {c.get('book','')}, topic: {c.get('topic','')})\n{c.get('text','')}"
            for j, c in enumerate(book_chunks)
        )
        pyq_material = "\n\n".join(
            f"[{j+1}]\n{p.get('text','')}"
            for j, p in enumerate(pyq_examples)
        ) if pyq_examples else "(No PYQ examples — use standard UKSSSC framing.)"

        system = GEN_SYSTEM.format(
            topic=topic, subject=subject,
            pyq_examples=pyq_material, book_chunks=book_material,
        )

        # Generate in sub-batches if q > MAX_QUESTIONS_PER_CALL (e.g. 500q / 50 topics
        # = 10q per topic; Sarvam batch=4 means 3 calls per topic). Top-up within the
        # topic if validation drops some questions.
        topic_out = 0
        topic_attempts = 0
        max_topic_attempts = max(4, math.ceil(q / max(1, MAX_QUESTIONS_PER_CALL)) * 2)

        while topic_out < q and topic_attempts < max_topic_attempts:
            need = q - topic_out
            batch = min(need, MAX_QUESTIONS_PER_CALL)
            user = (
                f"Generate exactly {batch} questions about the topic '{topic}'. "
                f"Each question must test a DIFFERENT specific fact from the study material."
            )
            try:
                if GEN_PROVIDER == "sarvam":
                    text = _gen_batch_sarvam(system, user, batch)
                else:
                    text = _gen_batch_anthropic(system, user, batch)
                parsed = _parse_json_array(text) or _repair_json(text)
                accepted = _accept(parsed, src_books)
                topic_out += accepted
            except RuntimeError as e:
                logger.warning("TOPIC %r batch failed: %s", topic, e)
                break
            topic_attempts += 1

        logger.info("TOPIC %r | quota=%d generated=%d", topic, q, topic_out)

    # Top-up: if total is still short (topic with no chunks, validation drops),
    # cycle through topics that have material and ask for 1 more question each.
    topup_attempts = 0
    max_topup = len(topics) * 2
    while len(out) < count and topup_attempts < max_topup:
        topic = topics[topup_attempts % n_topics]
        bucket = buckets[topic]
        if not bucket["book_chunks"]:
            topup_attempts += 1
            continue
        src_books = sorted({c.get("book", "") for c in bucket["book_chunks"] if c.get("book")})
        book_material = "\n\n".join(
            f"[{j+1}] {c.get('text','')}" for j, c in enumerate(bucket["book_chunks"])
        )
        pyq_material = "\n\n".join(
            p.get("text", "") for p in bucket["pyq_examples"]
        ) or "(No PYQ examples.)"
        system = GEN_SYSTEM.format(
            topic=topic, subject=subject,
            pyq_examples=pyq_material, book_chunks=book_material,
        )
        user = "Generate exactly 1 question about this topic."
        try:
            if GEN_PROVIDER == "sarvam":
                text = _gen_batch_sarvam(system, user, 1)
            else:
                text = _gen_batch_anthropic(system, user, 1)
            _accept(_parse_json_array(text), src_books)
        except RuntimeError:
            pass
        topup_attempts += 1

    if len(out) < count:
        logger.warning(
            "generate: only %d/%d questions produced for '%s'.",
            len(out), count, subject,
        )

    for i, q in enumerate(out, 1):
        q["n"] = i
    return out


def _gen_batch_anthropic(system: str, user: str, count: int) -> str:
    msg = _client().messages.create(
        model=GEN_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user}],
    )
    if msg.stop_reason == "max_tokens":
        raise RuntimeError(
            f"{GEN_MODEL} hit the {MAX_OUTPUT_TOKENS}-token cap generating {count} questions."
        )
    u = msg.usage
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
    logger.info(
        "BATCH model=%s count=%d | input=%d cache_read=%d cache_write=%d output=%d | "
        "tokens_per_q=%.1f",
        GEN_MODEL, count, u.input_tokens, cache_read, cache_write, u.output_tokens,
        u.output_tokens / count if count else 0,
    )
    return msg.content[0].text.strip() if msg.content else ""


def _gen_batch_sarvam(system: str, user: str, count: int) -> str:
    extra = {"reasoning_effort": os.environ.get("SARVAM_REASONING", "low")}
    try:
        resp = _sarvam_client().chat.completions.create(
            model=SARVAM_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **extra,
        )
    except TypeError:
        resp = _sarvam_client().chat.completions.create(
            model=SARVAM_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    choice = resp.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError(
            f"{SARVAM_MODEL} hit the {MAX_OUTPUT_TOKENS}-token cap generating {count} questions."
        )
    u = resp.usage
    logger.info(
        "BATCH model=%s count=%d | input=%d output=%d | tokens_per_q=%.1f",
        SARVAM_MODEL, count,
        getattr(u, "prompt_tokens", 0), getattr(u, "completion_tokens", 0),
        (getattr(u, "completion_tokens", 0) / count) if count else 0,
    )
    return (choice.message.content or "").strip()


# ── JSON repair (Haiku) ───────────────────────────────────────────────────────

_JSON_REPAIR_SYSTEM = (
    "You are a JSON repair tool. The user will send malformed or truncated JSON. "
    "Return ONLY the repaired valid JSON array. No prose, no markdown fences, no explanation."
)


def _repair_json(text: str) -> list:
    """If _parse_json_array fails, ask Haiku to repair the JSON structure.
    Haiku touches structure only — it never rewrites Hindi content."""
    try:
        msg = _client().messages.create(
            model=HAIKU,
            max_tokens=4096,
            system=_JSON_REPAIR_SYSTEM,
            messages=[{"role": "user", "content": text}],
        )
        repaired = msg.content[0].text.strip() if msg.content else ""
        result = _parse_json_array(repaired)
        logger.info("JSON_REPAIR recovered %d questions", len(result))
        return result
    except Exception as e:
        logger.warning("JSON_REPAIR failed: %s", e)
        return []


# ── orchestrator ─────────────────────────────────────────────────────────────

async def generate_questions(subject: str, count: int) -> list[dict]:
    """subject + count -> list of Question dicts (n, stem, options, answer, ...)."""
    topics = await _extract_topics(subject, count)
    buckets = await _collect_material(topics, subject)

    # Fail if every topic came back empty (subject has no corpus)
    if not any(b["book_chunks"] for b in buckets.values()):
        raise RuntimeError(
            f"No study material found for subject '{subject}'. "
            f"Ensure book_chunks has content for this subject."
        )

    questions = _gen_questions(subject, count, buckets)
    if not questions:
        raise RuntimeError(
            f"Generation produced no valid questions for subject '{subject}'."
        )
    return questions


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_json_array(text: str) -> list:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip()
    start, end = t.find("["), t.rfind("]")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    try:
        data = json.loads(t)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
