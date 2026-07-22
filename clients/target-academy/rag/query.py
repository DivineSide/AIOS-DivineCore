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
import re
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


DB_CONNECT_TIMEOUT = 10   # seconds — TCP connect ceiling, see below
DB_STATEMENT_TIMEOUT_MS = 30_000   # 30s — per-query ceiling, enforced server-side


def _db():
    conn = getattr(_thread_local, "conn", None)
    if conn is None or conn.closed:
        url = os.environ.get("SUPABASE_DB_URL", "")
        if not url:
            raise RuntimeError("SUPABASE_DB_URL not set in .env")
        # psycopg2.connect() has NO default timeout on TCP connect or query
        # execution — a network partition or a wedged query blocks forever,
        # and since _db() is called via asyncio.to_thread inside
        # asyncio.gather (generate.py's waves), one stuck connection hangs
        # that entire wave with no ceiling. connect_timeout bounds the
        # connect phase; statement_timeout (a session GUC, enforced by
        # Postgres itself, not the client) bounds every query after that.
        conn = psycopg2.connect(url, connect_timeout=DB_CONNECT_TIMEOUT,
                                options=f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}")
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
                threshold: float, format: str | None = None,
                exam: str | None = None) -> list[dict]:
    """Semantic search on pyq_chunks — same cosine similarity as book_passages
    but hits the PYQ table. Returns questions whose meaning is close to the
    query embedding, preserving framing + distractor style. Optional `format`
    filter ("match", "assertion", ...) returns only that question format —
    used to hand the generator real examples of the exact format it must write.

    Optional `exam` filter restricts style examples to THIS exam's own real
    papers (exam column added 2026-07-22, backfilled from source_file) — a
    vdo-vpdo paper's match/statement examples must come from vdo-vpdo's own
    past papers, not from group-c's or driver's, which have a totally
    different real format mix. Without this, exam-mode generation could draw
    its "how does a match question look" example from an unrelated exam."""
    conn = _db()
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    fmt_where = "AND format = %s" if format else ""
    exam_where = "AND exam = %s" if exam else ""
    sql = f"""
        SELECT
            chunk_text,
            source_file,
            answer,
            format,
            1 - (embedding <=> %s::vector) AS similarity
        FROM pyq_chunks
        WHERE subject = %s {fmt_where} {exam_where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    params = [vec_str, subject]
    if format:
        params.append(format)
    if exam:
        params.append(exam)
    params += [vec_str, top_k * 2]
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
    exam: str | None = None,
) -> list[dict]:
    """Semantic search on pyq_chunks for past questions relevant to a topic.
    `exam` (exam mode only) narrows style examples to that exam's own real
    papers — see _pyq_search. Returns [] on any error (table may not exist
    yet — fail soft)."""
    try:
        embedding = await asyncio.to_thread(_embed, topic)
        return await asyncio.to_thread(_pyq_search, embedding, subject, top_k,
                                       threshold, format, exam)
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


# ── hybrid retrieval (dense + lexical) ─────────────────────────────────────────
# WHY: pure dense cosine misses exact-token facts (a specific year, a proper
# noun, an act name) — it matches on MEANING and blurs precisely the tokens an
# exam fact hinges on. It also loses recall when the retrieved passage simply
# doesn't contain the answer (measured 2026-07-15: Sarvam hallucinated 15% of
# questions, all on thin/off-target passages). Adding a Postgres full-text
# (BM25-style) channel and fusing the two rankings recovers those cases.
#
# Postgres 'simple' config tokenises Devanagari correctly (verified), so no
# language pack is needed. Fusion is Reciprocal Rank Fusion (RRF): rank-based,
# parameter-free, and robust to the two scores being on different scales.
# All of this runs IN the database — zero extra API cost.

RRF_K = 60          # standard RRF constant; smooths rank contributions
HYBRID = os.environ.get("RAG_HYBRID", "0") == "1"
HYDE   = os.environ.get("RAG_HYDE", "0") == "1"
HYDE_MODEL = os.environ.get("RAG_HYDE_MODEL", "gpt-5.4-nano")


def _hybrid_search(embedding: list[float], query_text: str, top_k: int,
                   threshold: float, subject: str | None = None) -> list[dict]:
    """Dense cosine + lexical full-text, fused by RRF. Pulls a wide candidate
    pool from each channel, ranks each, then combines rank positions. A passage
    surfaced by EITHER channel can win — that's the point: dense catches
    paraphrase, lexical catches exact tokens."""
    conn = _db()
    vec = "[" + ",".join(str(x) for x in embedding) + "]"
    subj_where = "WHERE subject = %s" if subject else ""
    pool = max(top_k * 5, 20)   # candidate pool per channel
    # Dense channel: nearest by cosine.
    dense_sql = f"""
        SELECT id, book_name, subject, topic, passage_text,
               1 - (embedding <=> %s::vector) AS sim
        FROM book_passages {subj_where}
        ORDER BY embedding <=> %s::vector LIMIT %s"""
    # Lexical channel: full-text rank on the same query tokens.
    lex_where = "to_tsvector('simple', passage_text) @@ plainto_tsquery('simple', %s)"
    lex_sql = f"""
        SELECT id, book_name, subject, topic, passage_text,
               ts_rank(to_tsvector('simple', passage_text),
                       plainto_tsquery('simple', %s)) AS rnk
        FROM book_passages
        WHERE {lex_where} {('AND subject = %s' if subject else '')}
        ORDER BY rnk DESC LIMIT %s"""
    with conn.cursor() as cur:
        cur.execute(dense_sql, [vec, vec, pool] if not subject else [vec, subject, vec, pool])
        dense = cur.fetchall()
        lp = [query_text, query_text, pool] if not subject else [query_text, query_text, subject, pool]
        cur.execute(lex_sql, lp)
        lex = cur.fetchall()

    # RRF fuse: score = sum over channels of 1/(RRF_K + rank)
    scores: dict = {}
    meta: dict = {}
    for rank, row in enumerate(dense):
        rid = row[0]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (RRF_K + rank)
        meta[rid] = row
    for rank, row in enumerate(lex):
        rid = row[0]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (RRF_K + rank)
        meta.setdefault(rid, row)
    ordered = sorted(scores, key=lambda r: scores[r], reverse=True)

    out = []
    for rid in ordered[:top_k]:
        _id, book, subj, topic, text, score = meta[rid]
        out.append({"book": book, "subject": subj or "", "topic": topic or "",
                    "text": text, "similarity": round(float(scores[rid]), 4)})
    return out


_HYDE_SYS = ("Write ONE short factual Hindi sentence that would plausibly be the "
             "answer passage for the given exam topic. Invent nothing verifiable-"
             "critical; just mirror the STYLE and vocabulary of a textbook sentence "
             "on that topic. Output only the sentence.")


def _hyde_expand(topic: str) -> str:
    """HyDE: turn the topic into a hypothetical answer sentence, so we embed
    something shaped like the target PASSAGE instead of like a query. Cheap
    model; failure falls back to the raw topic."""
    try:
        r = _oai().chat.completions.create(
            model=HYDE_MODEL, max_completion_tokens=120,
            messages=[{"role": "system", "content": _HYDE_SYS},
                      {"role": "user", "content": f"विषय: {topic}"}])
        s = (r.choices[0].message.content or "").strip()
        return f"{topic}\n{s}" if s else topic
    except Exception:
        return topic


# Same impossible-sequence signatures as DsideOS/worker/validate_gen.py's
# _garble_hit, PLUS orphan_matra — duplicated (not imported, different import
# path) — keep both files in sync if either changes. orphan_matra is too
# noisy for a HARD per-field reject (validate_gen leaves it out: a bullet
# list item can look like a false hit) but is fine as a RANKING signal here —
# a passage with several orphan matras nearby is real evidence of damage even
# if any single instance might be a false positive.
_GARBLE_RX = re.compile(
    r"्[ा-ौॢॣ]"          # halant + vowel sign (impossible — halant only joins consonants)
    r"|््"                # double halant
    r"|[॒॑]"              # Vedic accent marks in exam prose
    r"|<[ऀ-ॿ]|[ऀ-ॿ]>"     # angle bracket wrapping Devanagari
    r"|(?:^|[\s(«»])[ा-ौ]"  # matra with no preceding consonant
)
# Separate class: not a composition violation, a REPETITION anomaly — e.g.
# "्ण्ण्ण्ण्ण्ण्ण्ण्ण्ण" (table-border/layout OCR artifact repeating one
# consonant+halant many times). _GARBLE_RX has no opinion on this (each
# halant-consonant pair is individually legal); this catches it separately.
_REPEAT_RX = re.compile(r"(.्)\1{3,}")   # same halant-joined char, 4+ times running


def _garble_score(text: str) -> float:
    """Garble-signature hit density (hits per 100 chars) — used only to RANK
    candidates (most-garbled last), never to reject one outright. Density,
    not a raw count: repeated-conjunct garbage (े.g. "्ण्ण्ण्ण्ण्ण्ण्ण्ण्ण्ण्ण्ण्ण")
    packs many signature instances into few characters, but consecutive hits
    share boundary characters so a plain non-overlapping findall() undercounts
    it — re.finditer with overlap (step back 1 char per match) catches that."""
    text = text or ""
    if not text:
        return 0.0
    hits, pos = 0, 0
    while pos < len(text):
        m = _GARBLE_RX.search(text, pos)
        if not m:
            break
        hits += 1
        pos = m.start() + 1   # step by 1, not m.end(), so overlapping runs all count
    repeat_hits = sum(m.end() - m.start() for m in _REPEAT_RX.finditer(text))
    return 100.0 * (hits + repeat_hits) / len(text)


async def passage_lookup(
    topic: str,
    subject: str | None = None,
    top_k: int = 4,
    threshold: float = 0.25,
) -> list[dict]:
    """Generation-side retrieval: multi-fact passages from book_passages.
    Same result shape as rag_lookup, so it's a drop-in for generate.py.

    Retrieval mode is env-flagged (default = original dense-only path, unchanged):
      RAG_HYBRID=1  fuse dense + lexical (RRF)  — recovers exact-token / thin-passage misses
      RAG_HYDE=1    embed a hypothetical answer sentence instead of the raw topic

    Over-fetches by a margin and drops the most garble-heavy candidates before
    truncating to top_k — a passage riddled with OCR-impossible sequences
    (un-re-OCR'd hindi/general-gk book tier) makes a worse fact source even
    when it's a good semantic match, and every extra retry it causes is a
    live-cost, not just a quality issue. Never drops below top_k candidates
    even if all of them are somewhat garbled — thin retrieval beats none.
    Returns [] on any error (fail soft — e.g. table not built yet)."""
    try:
        embed_text = await asyncio.to_thread(_hyde_expand, topic) if HYDE else topic
        embedding = await asyncio.to_thread(_embed, embed_text)
        fetch_k = top_k + 4
        if HYBRID:
            candidates = await asyncio.to_thread(_hybrid_search, embedding, topic,
                                                 fetch_k, threshold, subject)
        else:
            candidates = await asyncio.to_thread(_passage_search, embedding, fetch_k,
                                                 threshold, subject)
        candidates.sort(key=lambda p: _garble_score(p.get("passage_text", "")))
        return candidates[:top_k]
    except Exception:
        return []


async def pyq_lookup(subject: str, top_k: int = 20,
                     exam: str | None = None) -> list[dict]:
    """Random sample of a subject's real PYQs — used by generate.py's
    _extract_topics() as the seed set an LLM summarizes into distinct exam
    topics. Not a stand-in for pyq_rag_lookup(), which does semantic search
    for a single already-chosen topic's style examples; this one is for
    discovering the topic taxonomy in the first place, so a random (not
    semantic) sample is the correct input.

    Optional `exam` restricts the sample to that exam's own papers — in exam
    mode this is a thin fallback (the official syllabus is the primary topic
    source, see syllabus.py) but should still never infer topics from a
    different exam's PYQs."""
    try:
        conn = _db()
        exam_where = "AND exam = %s" if exam else ""
        sql = f"""
            SELECT chunk_text, source_file
            FROM pyq_chunks
            WHERE subject = %s {exam_where}
            ORDER BY RANDOM()
            LIMIT %s
        """
        params = [subject] + ([exam] if exam else []) + [top_k]
        with conn.cursor() as cur:
            cur.execute(sql, params)
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
