# -*- coding: utf-8 -*-
"""
RAG query interface — embed a question, cosine-search Supabase, return passages.

Standalone and importable:
    from query import rag_lookup
    passages = await rag_lookup(stem, options)
    # returns: [{"book": str, "subject": str, "topic": str, "text": str, "similarity": float}]

CLI:
    python query.py "उत्तराखंड का प्रथम राज्यपाल कौन था?"
    python query.py "some question" --top 5 --threshold 0.25
"""

import asyncio
import io
import os
import sys
import threading
from pathlib import Path

# Only rewrap stdout/stderr when running as CLI — Celery's LoggingProxy has no .buffer
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

BASE = Path(__file__).resolve().parents[1]

EMBED_MODEL       = "text-embedding-3-small"
DEFAULT_TOP_K     = 5
DEFAULT_THRESHOLD = 0.25


def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return

_load_env()
_openai: OpenAI | None = None

# psycopg2 connections are NOT safe for concurrent use across threads. The
# generate pipeline runs _search via asyncio.to_thread and fires several lookups
# concurrently, so each thread gets its own connection (thread-local) rather than
# sharing one global socket. The OpenAI client is thread-safe, so it stays shared.
_thread_local = threading.local()


def _oai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI()
    return _openai


def _db():
    conn = getattr(_thread_local, "conn", None)
    if conn is None or conn.closed:
        url = os.environ.get("SUPABASE_DB_URL", "")
        if not url:
            raise RuntimeError("SUPABASE_DB_URL not set in .env")
        conn = psycopg2.connect(url)
        _thread_local.conn = conn
    return conn


def _embed(text: str) -> list[float]:
    resp = _oai().embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


def _search(embedding: list[float], top_k: int, threshold: float,
            subject: str | None = None) -> list[dict]:
    # Searches book_passages (NOT book_chunks): since 2026-07-13 embeddings live
    # only on the merged passage view — book_chunks is text-only canonical source
    # (its 300MB of chunk-level vectors were dropped to fit the Supabase quota,
    # and passages are the cleaner corpus anyway: junk-filtered, multi-fact).
    conn = _db()
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    # optional subject filter — when set, only search that subject's books
    where = "WHERE subject = %s" if subject else ""
    sql = f"""
        SELECT
            book_name,
            subject,
            topic,
            passage_text,
            1 - (embedding <=> %s::vector) AS similarity
        FROM book_passages
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    params = ([vec_str, subject, vec_str, top_k * 2] if subject
              else [vec_str, vec_str, top_k * 2])
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    results = []
    for book_name, subject, topic, chunk_text, similarity in rows:
        if similarity >= threshold:
            results.append({
                "book":       book_name,
                "subject":    subject or "",
                "topic":      topic or "",
                "text":       chunk_text,
                "similarity": round(float(similarity), 4),
            })
        if len(results) >= top_k:
            break
    return results


async def rag_lookup(
    stem: str,
    options: list[str] | None = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
    subject: str | None = None,
) -> list[dict]:
    query = stem
    if options:
        query = f"{stem} {' '.join(options)}"
    embedding = await asyncio.to_thread(_embed, query)
    return await asyncio.to_thread(_search, embedding, top_k, threshold, subject)


def _pyq_search(embedding: list[float], subject: str, top_k: int,
                threshold: float, format: str | None = None) -> list[dict]:
    """Semantic search on pyq_chunks — same cosine similarity as book_passages
    but hits the PYQ table. Returns questions whose meaning is close to the
    query embedding, preserving framing + distractor style. Optional `format`
    filter ("match", "assertion", ...) returns only that question format —
    used to hand the generator real examples of the exact format it must write."""
    conn = _db()
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    fmt_where = "AND format = %s" if format else ""
    sql = f"""
        SELECT
            chunk_text,
            source_file,
            answer,
            format,
            1 - (embedding <=> %s::vector) AS similarity
        FROM pyq_chunks
        WHERE subject = %s {fmt_where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    params = ([vec_str, subject, format, vec_str, top_k * 2] if format
              else [vec_str, subject, vec_str, top_k * 2])
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    results = []
    for chunk_text, source_file, answer, fmt, similarity in rows:
        if similarity >= threshold:
            results.append({
                "text":        chunk_text,
                "source_file": source_file,
                "answer":      answer,
                "format":      fmt,
                "similarity":  round(float(similarity), 4),
            })
        if len(results) >= top_k:
            break
    return results


async def pyq_rag_lookup(
    topic: str,
    subject: str,
    top_k: int = 5,
    threshold: float = 0.20,
    format: str | None = None,
) -> list[dict]:
    """Semantic search on pyq_chunks for past questions relevant to a topic.
    Returns [] on any error (table may not exist yet — fail soft)."""
    try:
        embedding = await asyncio.to_thread(_embed, topic)
        return await asyncio.to_thread(_pyq_search, embedding, subject, top_k,
                                       threshold, format)
    except Exception:
        return []


def _passage_search(embedding: list[float], top_k: int, threshold: float,
                    subject: str | None = None) -> list[dict]:
    """Cosine search on book_passages — the merged, generation-grade view of the
    corpus (multi-fact passages instead of one-line fragments). Exact scan, no
    index (small table, perfect recall). rag_lookup hits the same table now;
    this variant differs only in defaults + fail-soft behaviour."""
    conn = _db()
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    where = "WHERE subject = %s" if subject else ""
    sql = f"""
        SELECT
            book_name,
            subject,
            topic,
            passage_text,
            1 - (embedding <=> %s::vector) AS similarity
        FROM book_passages
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    params = ([vec_str, subject, vec_str, top_k * 2] if subject
              else [vec_str, vec_str, top_k * 2])
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    results = []
    for book_name, subj, topic, text, similarity in rows:
        if similarity >= threshold:
            results.append({
                "book":       book_name,
                "subject":    subj or "",
                "topic":      topic or "",
                "text":       text,
                "similarity": round(float(similarity), 4),
            })
        if len(results) >= top_k:
            break
    return results


async def passage_lookup(
    topic: str,
    subject: str | None = None,
    top_k: int = 4,
    threshold: float = 0.25,
) -> list[dict]:
    """Generation-side retrieval: multi-fact passages from book_passages.
    Same result shape as rag_lookup, so it's a drop-in for generate.py.
    Returns [] on any error (fail soft — e.g. table not built yet)."""
    try:
        embedding = await asyncio.to_thread(_embed, topic)
        return await asyncio.to_thread(_passage_search, embedding, top_k,
                                       threshold, subject)
    except Exception:
        return []


async def pyq_lookup(subject: str, top_k: int = 20) -> list[dict]:
    """Random fetch fallback — kept for backwards compatibility but no longer
    used by the generate pipeline (pyq_rag_lookup replaced it)."""
    try:
        conn = _db()
        sql = """
            SELECT chunk_text, source_file
            FROM pyq_chunks
            WHERE subject = %s
            ORDER BY RANDOM()
            LIMIT %s
        """
        with conn.cursor() as cur:
            cur.execute(sql, (subject, top_k))
            rows = cur.fetchall()
        return [{"text": chunk_text, "source_file": source_file}
                for chunk_text, source_file in rows]
    except Exception:
        return []


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print('usage: python query.py "<question>" [--top N] [--threshold 0.25]')
        sys.exit(1)

    question  = args[0]
    top_k     = DEFAULT_TOP_K
    threshold = DEFAULT_THRESHOLD

    if "--top" in args:
        top_k = int(args[args.index("--top") + 1])
    if "--threshold" in args:
        threshold = float(args[args.index("--threshold") + 1])

    async def run():
        print(f"Query    : {question}")
        print(f"Top-k    : {top_k}  Threshold: {threshold}\n")
        passages = await rag_lookup(question, top_k=top_k, threshold=threshold)
        if not passages:
            print("No passages found above threshold.")
            return
        for i, p in enumerate(passages, 1):
            print(f"[{i}] book={p['book']}  subject={p['subject']}  topic={p['topic']}  sim={p['similarity']}")
            print(f"    {p['text'][:300]}{'...' if len(p['text']) > 300 else ''}")
            print()

    asyncio.run(run())


if __name__ == "__main__":
    main()
