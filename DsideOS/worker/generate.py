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
import json
import os
import sys
from pathlib import Path

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

# RAG depth — how many results to fetch per topic from each table
TOPICS_DIVISOR = 5       # ~N/5 distinct topics from Haiku
BOOK_TOP_K = 3           # book passages per topic
PYQ_TOP_K = 3            # PYQ style examples per topic
BOOK_THRESHOLD = 0.25
PYQ_THRESHOLD = 0.20     # slightly lower — PYQ phrasing varies more than book text

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

Subject: "{subject}". Generate exactly {count} multiple-choice questions.

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
        f"no prose. Example: [\"topic one\", \"topic two\"]"
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

    for topic in topics:
        # semantic search on book_chunks for factual grounding
        passages = await rag.rag_lookup(
            stem=topic, top_k=BOOK_TOP_K, threshold=BOOK_THRESHOLD, subject=subject
        )
        for p in passages:
            key = (p.get("book", ""), p.get("topic", ""))
            if key not in seen_books:
                seen_books.add(key)
                book_chunks.append({**p, "from_topic": topic})

        # semantic search on pyq_chunks for style + framing reference
        pyqs = await rag.pyq_rag_lookup(
            topic=topic, subject=subject, top_k=PYQ_TOP_K, threshold=PYQ_THRESHOLD
        )
        for p in pyqs:
            key = (p.get("source_file", ""), p.get("text", "")[:80])
            if key not in seen_pyqs:
                seen_pyqs.add(key)
                pyq_examples.append({**p, "from_topic": topic})

    return book_chunks, pyq_examples


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

    system = GEN_SYSTEM.format(
        subject=subject, count=count,
        pyq_examples=pyq_material, book_chunks=book_material,
    )
    msg = _client().messages.create(
        model=SONNET,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": f"Generate exactly {count} questions now."}],
    )
    questions = _parse_json_array(msg.content[0].text.strip())

    src_books = sorted({c.get("book", "") for c in book_chunks if c.get("book")})
    out = []
    for i, q in enumerate(questions, 1):
        if not isinstance(q, dict) or not q.get("stem"):
            continue
        q["n"] = i
        q.setdefault("options", [])
        if src_books and not q.get("sources"):
            q["sources"] = src_books
        out.append(q)
    return out


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
    return _gen_questions(subject, count, book_chunks, pyq_examples)


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
