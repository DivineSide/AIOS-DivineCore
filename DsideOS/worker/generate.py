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

import query as rag  # noqa: E402  (pyq_lookup, rag_lookup)

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

# how many topics to mine relative to question count, and RAG depth per topic
TOPICS_DIVISOR = 5      # ~N/5 distinct topics
RAG_TOP_K = 3
RAG_THRESHOLD = 0.25
PYQ_SAMPLE = 20

# readable subject names for the fallback topic when there are no PYQs yet
SUBJECT_LABELS = {
    "uk-history": "उत्तराखंड का इतिहास",
    "uk-geography": "उत्तराखंड का भूगोल",
    "uk-culture": "उत्तराखंड की संस्कृति",
    "uk-general-studies": "उत्तराखंड सामान्य अध्ययन",
    "general-gk": "सामान्य ज्ञान",
    "hindi": "सामान्य हिंदी",
}

GEN_SYSTEM = """You are an Indian competitive-exam question writer for UKSSSC, UPPSC, and similar
state PSC papers.

You have been given excerpts from official study material for the subject: "{subject}".
Generate exactly {count} multiple-choice questions based ONLY on information present
in these excerpts. Do not invent facts.

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

STUDY MATERIAL:
{chunks}"""


def _client() -> anthropic.Anthropic:
    # ANTHROPIC_API_KEY is put into the env by tasks.py / settings before import
    return anthropic.Anthropic()


# ── Phase 1 — PYQ -> topics (Haiku) ──────────────────────────────────────────

async def _extract_topics(subject: str, count: int) -> list[str]:
    n_topics = max(1, count // TOPICS_DIVISOR)
    pyqs = await rag.pyq_lookup(subject, top_k=PYQ_SAMPLE)

    if not pyqs:
        # no PYQs ingested yet — fall back to a single subject-derived topic so
        # Phase 2/3 still run (the handoff explicitly asks for this).
        return [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]

    examples = "\n".join(f"- {p['text']}" for p in pyqs)
    prompt = (
        f"These are real exam questions for the subject '{subject}':\n\n{examples}\n\n"
        f"What distinct topics/concepts do these exam questions test? "
        f"Return exactly {n_topics} topic strings as a JSON array of strings, "
        f"no prose. Example: [\"topic one\", \"topic two\"]"
    )
    client = _client()
    msg = client.messages.create(
        model=HAIKU,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    topics = _parse_json_array(text)
    # keep only non-empty strings; fall back if parsing yielded nothing
    topics = [t for t in topics if isinstance(t, str) and t.strip()]
    if not topics:
        return [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]
    return topics[:n_topics]


# ── Phase 2 — topics -> book chunks (RAG, no LLM) ────────────────────────────

async def _collect_chunks(topics: list[str], subject: str) -> list[dict]:
    seen = set()
    collected = []
    for topic in topics:
        passages = await rag.rag_lookup(
            stem=topic, top_k=RAG_TOP_K, threshold=RAG_THRESHOLD, subject=subject
        )
        for p in passages:
            key = (p.get("book", ""), p.get("topic", ""))
            if key in seen:
                continue
            seen.add(key)
            collected.append({**p, "from_topic": topic})
    return collected


# ── Phase 3 — chunks -> questions (Sonnet) ───────────────────────────────────

def _gen_questions(subject: str, count: int, chunks: list[dict]) -> list[dict]:
    material = "\n\n".join(
        f"[{i+1}] (book: {c.get('book','')}, topic: {c.get('topic','')})\n{c.get('text','')}"
        for i, c in enumerate(chunks)
    )
    system = GEN_SYSTEM.format(subject=subject, count=count, chunks=material)
    client = _client()
    msg = client.messages.create(
        model=SONNET,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user",
                   "content": f"Generate exactly {count} questions now."}],
    )
    text = msg.content[0].text.strip()
    questions = _parse_json_array(text)

    # normalise: renumber, attach sources for traceability, keep only valid shapes
    out = []
    src_books = sorted({c.get("book", "") for c in chunks if c.get("book")})
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
    chunks = await _collect_chunks(topics, subject)
    if not chunks:
        # no study material matched — surface a clear error rather than empty paper
        raise RuntimeError(
            f"No study material found for subject '{subject}'. "
            f"Ensure book_chunks has content for this subject."
        )
    return _gen_questions(subject, count, chunks)


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
