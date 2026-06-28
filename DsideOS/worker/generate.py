# -*- coding: utf-8 -*-
"""AI-generative question pipeline — subject + count -> N exam questions.

Four phases (per the generate-endpoint handoff):

  1. PYQ topic extraction (Haiku)  — sample real past questions for the subject,
     ask Haiku what concepts they test -> a short list of topic strings.
  2. Topic -> book content (RAG)    — for each topic, semantic-search book_chunks
     for the most relevant study material (no LLM).
  3. Generate questions (Sonnet)    — feed the collected book excerpts to Sonnet,
     get exactly N MCQs back as JSON.
  4. Build                          — handled by the caller (generate_task), which
     feeds the questions into the existing build pipeline.

This module only owns phases 1-3 and exposes one coroutine:

    questions = await generate_questions(subject, count)
    # -> list[dict] each matching the Question schema (n, stem, options, answer, ...)
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

import anthropic

# the RAG helpers live with the client corpus; import them by path (same pattern
# tasks.py uses to reach the pipeline).
REPO_ROOT = Path(__file__).resolve().parents[2]
RAG = REPO_ROOT / "clients" / "target-academy" / "rag"
if str(RAG) not in sys.path:
    sys.path.insert(0, str(RAG))

import query as rag  # noqa: E402  (pyq_rag_lookup, rag_lookup)

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
GEN_MODEL = HAIKU  # Anthropic model used when GEN_PROVIDER=anthropic

# ── Generation provider ──────────────────────────────────────────────────────
# "anthropic"-> Claude (HAIKU/SONNET above). Current default — keeps working with
#               no new credentials.
# "sarvam"   -> Sarvam's Hindi-native LLM (cleaner Devanagari, ~30x cheaper than
#               Haiku on output). OpenAI-compatible. Needs SARVAM_API_KEY.
# Flip via the GEN_PROVIDER env var on the worker — no code change needed. Set
# GEN_PROVIDER=sarvam + SARVAM_API_KEY once the Sarvam key is provisioned.
GEN_PROVIDER = os.environ.get("GEN_PROVIDER", "anthropic").lower()
SARVAM_MODEL = os.environ.get("SARVAM_MODEL", "sarvam-105b")
SARVAM_BASE_URL = "https://api.sarvam.ai/v1"

# RAG depth — how many results to fetch per topic from each table
TOPICS_DIVISOR = 5       # ~N/5 distinct topics from Haiku
BOOK_TOP_K = 2           # book passages per topic (fallback fetches BOOK_TOP_K*3=6)
PYQ_TOP_K = 2            # PYQ style examples per topic; total capped at PYQ_CAP
PYQ_CAP = 12             # style saturates at ~8 examples; 12 gives a buffer
BOOK_THRESHOLD = 0.20
BOOK_FALLBACK_THRESHOLD = 0.15   # looser net for the empty-result fallback
PYQ_THRESHOLD = 0.20     # slightly lower — PYQ phrasing varies more than book text

# Sonnet output budget. Devanagari factual MCQs (stem + 4 options + reason,
# no solution) run ~220-280 output tokens. We batch at 25 questions per call
# (~25*270 ≈ 6750 tokens, safely under the 8192 cap). The stop_reason guard
# catches any overrun and fails loud — no silent truncation.
TOKENS_PER_QUESTION = 270
MAX_OUTPUT_TOKENS = 8192
MAX_QUESTIONS_PER_CALL = 25

VALID_ANSWERS = {"a", "b", "c", "d"}

# Fallback topic labels when no PYQs exist yet for a subject
SUBJECT_LABELS = {
    "uk-history":          "उत्तराखंड का इतिहास",
    "uk-geography":        "उत्तराखंड का भूगोल",
    "uk-culture":          "उत्तराखंड की संस्कृति",
    "uk-general-studies":  "उत्तराखंड सामान्य अध्ययन",
    "general-gk":          "सामान्य ज्ञान",
    "hindi":               "सामान्य हिंदी",
}

# The system prompt receives both PYQ examples (style) and book passages (facts).
# PYQ examples teach Sonnet HOW to frame questions; book passages teach it WHAT to say.
GEN_SYSTEM = """You are an Indian competitive-exam question writer for UKSSSC, UPPSC, and similar
state PSC papers.

You have been given:
1. REAL PAST EXAM QUESTIONS (PYQ EXAMPLES) — study these carefully. Mirror their:
   - Question framing and sentence structure
   - Hindi register and formality level
   - Option length and distractor style
   - Difficulty level and concept depth
2. STUDY MATERIAL — factual book excerpts. Every question you generate must be
   answerable from this material. Do not invent facts.

Subject: "{subject}". Generate the number of multiple-choice questions requested
in the user message.

RULES:
- Language: Hindi (Devanagari). English proper nouns stay in English.
- Each question: exactly 4 options (a), (b), (c), (d)
- Difficulty mix: 30% easy, 50% medium, 20% hard
- No repeated concepts across questions
- Distractors must be plausible — not obviously wrong
- For numerical/reasoning questions: include a worked solution in the "solution" field

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

━━━ STUDY MATERIAL (factual source) ━━━
{book_chunks}"""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


_sarvam = None


def _sarvam_client():
    """Lazily build the Sarvam client (OpenAI-compatible). Reused across batches."""
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
    """Use Haiku to derive N/5 distinct exam topics for the subject.
    Seeds Haiku with a random PYQ sample so it understands what this exam
    actually tests — not a generic topic list."""
    n_topics = max(1, count // TOPICS_DIVISOR)

    # seed with a small random sample just for topic discovery (cheap, no embedding)
    seed_pyqs = await rag.pyq_lookup(subject, top_k=15)
    if not seed_pyqs:
        return [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]

    examples = "\n".join(f"- {p['text'][:300]}" for p in seed_pyqs)
    prompt = (
        f"These are real exam questions for the subject '{subject}':\n\n{examples}\n\n"
        f"What distinct topics/concepts do these exam questions test? "
        f"Return exactly {n_topics} topic strings as a JSON array of strings, "
        f"no prose. Write each topic in Hindi (Devanagari script). "
        f"Example: [\"उत्तराखंड का गठन\", \"गढ़वाल राज्य का इतिहास\"]"
    )
    msg = _client().messages.create(
        model=HAIKU,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    topics = _parse_json_array(msg.content[0].text.strip())
    topics = [t for t in topics if isinstance(t, str) and t.strip()]
    if not topics:
        return [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]
    return topics[:n_topics]


# ── Phase 2 — topics -> book chunks + PYQ style examples (RAG, no LLM) ───────

async def _collect_material(topics: list[str], subject: str) -> tuple[list[dict], list[dict]]:
    """For each topic, semantic-search both tables in parallel:
    - book_chunks  → factual source material (what to say)
    - pyq_chunks   → real past questions on that topic (how to say it)
    Returns (book_chunks, pyq_examples) deduplicated."""
    seen_books = set()
    seen_pyqs = set()
    book_chunks = []
    pyq_examples = []

    # Each topic = two independent embedding round-trips (book + PYQ). Fire them
    # all concurrently — for count=100 (20 topics) this collapses 40 serial
    # network round-trips to ~1-2. Results are merged in topic order afterwards
    # so dedup stays deterministic. (Per-thread DB conns in query.py make the
    # underlying _search calls safe to run in parallel.)
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

    for topic, passages in zip(topics, book_results):
        for p in passages:
            _merge_book(p, topic, seen_books, book_chunks)

    for topic, pyqs in zip(topics, pyq_results):
        for p in pyqs:
            key = (p.get("source_file", ""), p.get("text", "")[:80])
            if key not in seen_pyqs:
                seen_pyqs.add(key)
                pyq_examples.append({**p, "from_topic": topic})

    pyq_examples = pyq_examples[:PYQ_CAP]

    # Fallback: trigger when retrieval is empty OR too thin to ground `count`
    # questions (topics were wrong-language / too abstract). Use the subject's
    # canonical Hindi label — English never embeds well against the Hindi corpus.
    min_chunks = max(1, len(topics))
    if len(book_chunks) < min_chunks:
        fallback_topic = SUBJECT_LABELS.get(subject, subject.replace("-", " "))
        passages = await rag.rag_lookup(
            stem=fallback_topic, top_k=BOOK_TOP_K * 3,
            threshold=BOOK_FALLBACK_THRESHOLD, subject=subject,
        )
        for p in passages:
            _merge_book(p, fallback_topic, seen_books, book_chunks)

    return book_chunks, pyq_examples


def _merge_book(p: dict, from_topic: str, seen_books: set, book_chunks: list) -> None:
    """Dedup a book passage by (book, topic) and append it once."""
    key = (p.get("book", ""), p.get("topic", ""))
    if key not in seen_books:
        seen_books.add(key)
        book_chunks.append({**p, "from_topic": from_topic})


# ── Phase 3 — book chunks + PYQ examples -> questions (Sonnet) ───────────────

def _gen_questions(subject: str, count: int,
                   book_chunks: list[dict], pyq_examples: list[dict]) -> list[dict]:
    book_material = "\n\n".join(
        f"[{i+1}] (book: {c.get('book','')}, topic: {c.get('topic','')})\n{c.get('text','')}"
        for i, c in enumerate(book_chunks)
    )
    pyq_material = "\n\n".join(
        f"[{i+1}] (topic: {p.get('from_topic','')})\n{p.get('text','')}"
        for i, p in enumerate(pyq_examples)
    ) if pyq_examples else "(No PYQ examples available yet — use standard UKSSSC framing.)"

    src_books = sorted({c.get("book", "") for c in book_chunks if c.get("book")})

    # Batch so a single call never approaches MAX_OUTPUT_TOKENS and truncates the
    # JSON. Hindi output is token-heavy — count=100 in one call would overrun.
    raw_questions: list[dict] = []
    remaining = count
    while remaining > 0:
        batch = min(remaining, MAX_QUESTIONS_PER_CALL)
        raw_questions.extend(_gen_batch(subject, batch, book_material, pyq_material))
        remaining -= batch

    # Validate + renumber. Drop anything the builders can't render: a question
    # needs a stem, exactly 4 options, and an answer letter in a-d. (Builders
    # index LABELS by the answer letter and assume 4 options — a bad row would
    # crash build_solution / build_deck, failing the whole job.)
    out = []
    n = 1
    for q in raw_questions:
        if not isinstance(q, dict) or not q.get("stem"):
            continue
        opts = q.get("options")
        if not isinstance(opts, list) or len(opts) != 4:
            continue
        ans = str(q.get("answer", "")).strip().lower()
        if ans not in VALID_ANSWERS:
            continue
        q["answer"] = ans
        q["n"] = n
        n += 1
        if src_books and not q.get("sources"):
            q["sources"] = src_books
        out.append(q)
    return out


def _gen_batch(subject: str, count: int,
               book_material: str, pyq_material: str) -> list[dict]:
    """One Sonnet call for up to MAX_QUESTIONS_PER_CALL questions.

    The system prompt (rules + PYQ examples + book material) is byte-identical
    across every batch of a single run — only the requested `count` changes, and
    that lives in the user message. We cache the system block so batches 2..N read
    the shared context at ~0.1x input cost instead of paying full price each time.
    For a 100-question paper (6 batches) this cuts Sonnet input spend by ~5/6 on
    the cached portion. Cache TTL is 5 min — comfortably longer than a full run.
    """
    system = GEN_SYSTEM.format(
        subject=subject,
        pyq_examples=pyq_material, book_chunks=book_material,
    )
    user = f"Generate exactly {count} questions now."
    if GEN_PROVIDER == "sarvam":
        text = _gen_batch_sarvam(system, user, count)
    else:
        text = _gen_batch_anthropic(system, user, count)
    return _parse_json_array(text)


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
    # A max_tokens stop means the JSON was cut mid-array — fail loud rather than
    # silently returning the [] that _parse_json_array gives for truncated input.
    if msg.stop_reason == "max_tokens":
        raise RuntimeError(
            f"{GEN_MODEL} hit the {MAX_OUTPUT_TOKENS}-token cap generating {count} "
            f"questions — output truncated. Lower MAX_QUESTIONS_PER_CALL."
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
    """Sarvam (Hindi-native, OpenAI-compatible). System+user as chat messages."""
    # Sarvam turns reasoning on by default, and reasoning tokens count toward the
    # completion budget — for straight JSON MCQ output we don't need it, and it
    # would eat into MAX_OUTPUT_TOKENS. Request minimal reasoning; tolerate SDKs
    # that don't accept the param.
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
        # older OpenAI client without reasoning_effort kwarg — retry without it
        resp = _sarvam_client().chat.completions.create(
            model=SARVAM_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    choice = resp.choices[0]
    # length finish_reason = truncated mid-array; fail loud like the Anthropic path.
    if choice.finish_reason == "length":
        raise RuntimeError(
            f"{SARVAM_MODEL} hit the {MAX_OUTPUT_TOKENS}-token cap generating {count} "
            f"questions — output truncated. Lower MAX_QUESTIONS_PER_CALL or raise the plan cap."
        )
    u = resp.usage
    logger.info(
        "BATCH model=%s count=%d | input=%d output=%d | tokens_per_q=%.1f",
        SARVAM_MODEL, count, getattr(u, "prompt_tokens", 0), getattr(u, "completion_tokens", 0),
        (getattr(u, "completion_tokens", 0) / count) if count else 0,
    )
    return (choice.message.content or "").strip()


# ── orchestrator ─────────────────────────────────────────────────────────────

async def generate_questions(subject: str, count: int) -> list[dict]:
    """subject + count -> list of Question dicts (n, stem, options, answer, ...)."""
    topics = await _extract_topics(subject, count)
    book_chunks, pyq_examples = await _collect_material(topics, subject)
    if not book_chunks:
        raise RuntimeError(
            f"No study material found for subject '{subject}'. "
            f"Ensure book_chunks has content for this subject."
        )
    questions = _gen_questions(subject, count, book_chunks, pyq_examples)
    if not questions:
        raise RuntimeError(
            f"Generation produced no valid questions for subject '{subject}' "
            f"(model output failed stem/options/answer validation)."
        )
    return questions


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_json_array(text: str) -> list:
    """Parse a JSON array out of a model response, tolerating markdown fences."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip()
    # slice to the outermost [...] if there's surrounding prose
    start, end = t.find("["), t.rfind("]")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    try:
        data = json.loads(t)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
