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
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
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
_db_conn = None


def _oai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI()
    return _openai


def _db():
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        url = os.environ.get("SUPABASE_DB_URL", "")
        if not url:
            raise RuntimeError("SUPABASE_DB_URL not set in .env")
        _db_conn = psycopg2.connect(url)
    return _db_conn


def _embed(text: str) -> list[float]:
    resp = _oai().embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


def _search(embedding: list[float], top_k: int, threshold: float) -> list[dict]:
    conn = _db()
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    sql = """
        SELECT
            book_name,
            subject,
            topic,
            chunk_text,
            1 - (embedding <=> %s::vector) AS similarity
        FROM book_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (vec_str, vec_str, top_k * 2))
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
) -> list[dict]:
    query = stem
    if options:
        query = f"{stem} {' '.join(options)}"
    embedding = await asyncio.to_thread(_embed, query)
    return await asyncio.to_thread(_search, embedding, top_k, threshold)


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
