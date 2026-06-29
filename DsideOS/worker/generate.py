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

# RAG depth — how many results to fetch per topic from each table.
# TOPICS_DIVISOR drives VARIETY: questions can only be as diverse as the topics
# we retrieve material for. At 5 (the old value) a 10-question paper drew from
# just 2 topics -> every question clustered on those (e.g. 4x Gardner). Aim for
# ~2 questions per topic so the spread is wide: 10q -> ~5 topics, 50q -> ~25.
TOPICS_DIVISOR = 2       # ~N/2 distinct topics (each yields ~2 questions)
BOOK_TOP_K = 3           # book passages per topic (fallback fetches BOOK_TOP_K*3=9)
PYQ_TOP_K = 2            # PYQ style examples per topic; total capped at PYQ_CAP
PYQ_CAP = 12             # style saturates at ~8 examples; 12 gives a buffer
BOOK_CAP = 30            # cap total book passages so big papers don't over-grow
                         # the prompt; 30 spans plenty of topics for variety
BOOK_THRESHOLD = 0.20
BOOK_FALLBACK_THRESHOLD = 0.15   # looser net for the empty-result fallback
PYQ_THRESHOLD = 0.20     # slightly lower — PYQ phrasing varies more than book text

# Sonnet output budget. Devanagari factual MCQs (stem + 4 options + reason,
# no solution) run ~220-280 output tokens. We batch at 25 questions per call
# (~25*270 ≈ 6750 tokens, safely under the 8192 cap). The stop_reason guard
# catches any overrun and fails loud — no silent truncation.
TOKENS_PER_QUESTION = 270
# Output budget + batch size are provider-aware:
#  - Anthropic: 8192 cap, 25 q/call (~25*270 ≈ 6750, safely under).
#  - Sarvam: the Starter tier caps max_tokens at 4096, AND sarvam-105b always
#    reasons (the reasoning tokens count toward the cap and vary ~700-3000 per
#    call). Verified: batches of 8-10 q return valid JSON under 4096; we use 8
#    for a safe margin. Override both via env for a paid Sarvam tier.
if GEN_PROVIDER == "sarvam":
    MAX_OUTPUT_TOKENS = int(os.environ.get("SARVAM_MAX_TOKENS", "4096"))
    MAX_QUESTIONS_PER_CALL = int(os.environ.get("SARVAM_BATCH", "8"))
else:
    MAX_OUTPUT_TOKENS = 8192
    MAX_QUESTIONS_PER_CALL = 25

# Hard cap on generation rounds. count/MAX_QUESTIONS_PER_CALL rounds are needed
# just to reach `count` once; this allows that many again as top-up headroom for
# dropped (invalid/duplicate) questions, so a normal short-fall is recovered but
# a subject that genuinely can't yield `count` distinct questions can't loop
# forever. ceil(count / batch) * 2, min 6.
def _max_gen_attempts(count: int) -> int:
    import math
    return max(6, math.ceil(count / max(1, MAX_QUESTIONS_PER_CALL)) * 2)

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
- VARIETY IS CRITICAL: every question must test a DIFFERENT fact, person, date,
  place, event or concept. Spread questions ACROSS the whole study material —
  do not cluster on one event or ask the same thing reworded. Never produce two
  questions with the same answer concept.
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
    # Cap book chunks too so a large paper (many topics) can't build a giant
    # prompt. The chunks are gathered in topic order, so this keeps a spread
    # across topics rather than over-weighting any single one.
    book_chunks = book_chunks[:BOOK_CAP]

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

    # Generate in batches (a single call can't hold `count` questions without
    # overrunning the token cap) and TOP UP until we have `count` VALID, UNIQUE
    # questions. Validation drops un-renderable rows (need a stem, exactly 4
    # options, answer a-d — a bad row would crash the builders) and dedup drops
    # near-duplicate stems; without a top-up loop those drops make the paper come
    # back short (ask 10, get 9). Each batch is told what's already been asked so
    # it diversifies. Capped at MAX_GEN_ATTEMPTS extra rounds so a subject that
    # genuinely can't yield `count` distinct questions can't loop forever.
    out: list[dict] = []
    seen_stems: set[str] = set()

    def _accept(batch_questions: list[dict]) -> None:
        for q in batch_questions:
            if len(out) >= count:
                return
            if not isinstance(q, dict) or not q.get("stem"):
                continue
            opts = q.get("options")
            if not isinstance(opts, list) or len(opts) != 4:
                continue
            ans = str(q.get("answer", "")).strip().lower()
            if ans not in VALID_ANSWERS:
                continue
            norm = " ".join(str(q["stem"]).split()).lower()  # dedup key
            if norm in seen_stems:
                continue
            seen_stems.add(norm)
            q["answer"] = ans
            if src_books and not q.get("sources"):
                q["sources"] = src_books
            out.append(q)

    attempts = 0
    max_attempts = _max_gen_attempts(count)
    while len(out) < count and attempts <= max_attempts:
        need = count - len(out)
        batch = min(need, MAX_QUESTIONS_PER_CALL)
        prior_stems = list(seen_stems)
        _accept(_gen_batch(subject, batch, book_material, pyq_material, avoid=prior_stems))
        attempts += 1

    if len(out) < count:
        logger.warning(
            "generate: only %d/%d unique valid questions after %d attempts for '%s' "
            "(study material may be too narrow).", len(out), count, attempts, subject,
        )

    # final renumber
    for i, q in enumerate(out, 1):
        q["n"] = i
    return out


def _gen_batch(subject: str, count: int,
               book_material: str, pyq_material: str,
               avoid: list[str] | None = None) -> list[dict]:
    """One model call for up to MAX_QUESTIONS_PER_CALL questions.

    The system prompt (rules + PYQ examples + book material) is byte-identical
    across every batch of a single run — only the user message changes. The
    cached system block lets batches 2..N read the shared context cheaply
    (Anthropic path). `avoid` is the list of stems already generated this run;
    we tell the model not to repeat them so batches diversify instead of all
    circling the same one or two topics.
    """
    system = GEN_SYSTEM.format(
        subject=subject,
        pyq_examples=pyq_material, book_chunks=book_material,
    )
    user = f"Generate exactly {count} questions now."
    if avoid:
        # cap the list so it can't blow the prompt; the most recent are the most
        # likely to be re-hit, so keep the tail.
        recent = avoid[-40:]
        joined = "\n".join(f"- {s}" for s in recent)
        user += (
            "\n\nThese questions were ALREADY generated for this paper. Do NOT "
            "repeat them or ask the same fact in different words. Cover DIFFERENT "
            "topics, people, dates, places and concepts from the study material:\n"
            + joined
        )
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
