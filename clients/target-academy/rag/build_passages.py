# -*- coding: utf-8 -*-
"""
build_passages — merge book_chunks fragments into generation-grade passages.

WHY (2026-07-12): the ingest chunker split text on printed lines, leaving
book_chunks as one-fact fragments (median 94-500 chars) plus ~4,900 junk/header
rows. Question generation needs multi-fact passages. The expensive intelligence
(topic boundaries, document order) was already paid for at ingest — this script
just coarsens the granularity: merge consecutive chunks of the same book until
a target size, drop junk, re-embed, store in book_passages. Cost: embeddings
only (~$0.05 for the whole corpus).

book_chunks stays canonical; book_passages is derived and rebuildable any time.

Usage:
    python build_passages.py --all --wipe          # full rebuild (default books)
    python build_passages.py --book kumau_ka_ethihas
    python build_passages.py --all --wipe --include-damaged   # after re-OCR lands

By default the 3 digit-corrupted uk-history books are EXCLUDED (their year facts
are OCR-mangled: 1790 -> 4790; see corpus_health.py). They enter book_passages
after their Sarvam re-OCR replaces them in book_chunks.
"""

import argparse
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

# Same embedding space as everything else in the DB. OpenRouter when a key is
# present (ingest.py's route), else the direct OpenAI key — identical vectors,
# the provider is just transport.
EMBED_BATCH = 64
DB_BATCH    = 50

# Merge tuning. A passage flushes once it crosses TARGET_CHARS; MAX_CHARS is a
# hard cap so one giant source chunk can't produce a bloated passage.
TARGET_CHARS = 800
MAX_CHARS    = 1600
# Junk floor: fragments shorter than this never contribute (page headers, stray
# titles). They are logged, not silently eaten.
MIN_CHUNK_CHARS = 30
# A text repeated more than this many times within one book is running-header
# noise ("उत्तराखंड का इततहास" x3), not content.
MAX_REPEATS = 2

# Promo/front-matter junk — found ranking #1 on the very first passage retrieval
# test (jardhari's copyright page + email + review plea merged into a "passage").
# A chunk containing any of these is publisher furniture, not study material.
import re
_PROMO = re.compile(
    r"@gmail\.com|@yahoo|youtube\.com|https?://|www\.|"
    r"copyright|all rights reserved|£|"
    r"हमारे\s+YouTube|जुड़ें\s+हमारे\s+साथ|निशुल्क\s+कोर्स|ननशुल्क",
    re.IGNORECASE)
# MCQ-dump sections (the jardhari books embed Topic-Wise MCQ lists: "Q19....
# A.… B.… C.… D.…"). Question dumps are the wrong SHAPE for factual substance —
# generation needs prose passages; style examples come from pyq_chunks.
_MCQ_Q = re.compile(r"Q\s*\d{1,3}\s*[.।]")
_MCQ_OPT = re.compile(r"(?:^|\s)[A-D]\s*[.)]\s*\S")
# Table-of-contents blocks: several "chapter 4-10 / 11-21" page ranges in one
# chunk. TOCs carry every chapter title, so they rank high on topic queries
# while containing zero facts (caught polluting the गोरखा retrieval test).
_TOC_RANGE = re.compile(r"\d{1,3}\s*[-–]\s*\d{1,3}")
_TOC_WORDS = re.compile(r"content\s+page|तिर्षय\s*सूची|विषय\s*सूची|अनुक्रम", re.IGNORECASE)
# Corrupted-year chunks: Tesseract reads a printed '1' as '4' or '7', producing
# impossible CE dates ("7370 ई०" = 1370, "(4625-4638)" = 1625-1638). A passage
# that TEACHES a wrong year is worse than a missing passage — the grounding
# gate would DEFEND the wrong year, since the source states it. BCE dates
# ("4000 ई० पू०") are real ancient-history facts and are exempt.
_BAD_YEAR = re.compile(r"\b[4-9][0-9]{3}\s*(?:में|तक|से|ई(?![.०]?\s*पू))")
_BAD_YEAR_RANGE = re.compile(r"\(\s*[0-9]{3,4}\s*[-–]\s*[4-9][0-9]{3}\s*\)")


def _is_junk_content(t: str) -> str | None:
    if _PROMO.search(t):
        return "promo"
    if _MCQ_Q.search(t) and len(_MCQ_OPT.findall(t)) >= 3:
        return "mcq_dump"
    if _TOC_WORDS.search(t) or len(_TOC_RANGE.findall(t)) >= 4:
        return "toc"
    if _BAD_YEAR.search(t) or _BAD_YEAR_RANGE.search(t):
        return "bad_year"
    return None

# Digit-corrupted books (Tesseract read printed '1' as '4'; ~600 chunks carry
# wrong years). Kept OUT of generation retrieval until their Sarvam re-OCR.
# BAHI302 graduated 2026-07-12: re-OCR'd via Sarvam (as "BAHI302.pdf"), 2/1338
# flagged chunks vs 239/1015 before.
DAMAGED_BOOKS = {
    "uttarakhand_ka_rajnaitik_itihas_ajay_rawat",
    "उत्तराखंड का इतिहास",
}


def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return


_load_env()
_client: OpenAI | None = None
_EMBED_MODEL: str | None = None


def _oai() -> OpenAI:
    global _client, _EMBED_MODEL
    if _client is None:
        router_key = os.environ.get("OPENROUTER_API_KEY", "")
        if router_key:
            _client = OpenAI(api_key=router_key, base_url="https://openrouter.ai/api/v1",
                             timeout=90, max_retries=5)
            _EMBED_MODEL = "openai/text-embedding-3-small"
        else:
            _client = OpenAI(timeout=90, max_retries=5)  # direct OPENAI_API_KEY
            _EMBED_MODEL = "text-embedding-3-small"
    return _client


def _db():
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set in .env")
    return psycopg2.connect(url, connect_timeout=30)


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


# ── merge ────────────────────────────────────────────────────────────────────

def merge_book(rows: list[tuple]) -> tuple[list[dict], dict]:
    """rows: [(id, topic, text)] in document (id) order for ONE book.
    Returns (passages, stats). Pure code — no LLM."""
    from collections import Counter
    norm_counts = Counter(_norm(t) for _, _, t in rows)

    passages: list[dict] = []
    stats = {"junk_short": 0, "junk_repeat": 0, "junk_promo": 0,
             "junk_mcq": 0, "junk_toc": 0, "junk_bad_year": 0, "kept_chunks": 0}

    cur_texts: list[str] = []
    cur_topics: list[str] = []
    cur_ids: list[int] = []
    cur_len = 0

    def flush():
        nonlocal cur_texts, cur_topics, cur_ids, cur_len
        if cur_texts:
            seen, topics = set(), []
            for t in cur_topics:
                tn = t.strip()
                if tn and tn not in seen:
                    seen.add(tn)
                    topics.append(tn)
            passages.append({
                "text": "\n".join(cur_texts),
                "topic": " | ".join(topics[:6]),
                "chunk_ids": cur_ids,
                "n_chunks": len(cur_ids),
            })
        cur_texts, cur_topics, cur_ids, cur_len = [], [], [], 0

    for cid, topic, text in rows:
        t = text.strip()
        if len(t) < MIN_CHUNK_CHARS:
            stats["junk_short"] += 1
            continue
        if norm_counts[_norm(t)] > MAX_REPEATS:
            stats["junk_repeat"] += 1
            continue
        junk = _is_junk_content(t)
        if junk == "promo":
            stats["junk_promo"] += 1
            continue
        if junk == "mcq_dump":
            stats["junk_mcq"] += 1
            continue
        if junk == "toc":
            stats["junk_toc"] += 1
            continue
        if junk == "bad_year":
            stats["junk_bad_year"] += 1
            continue
        stats["kept_chunks"] += 1
        # a single huge chunk that would blow the cap flushes what came before
        if cur_len and cur_len + len(t) > MAX_CHARS:
            flush()
        cur_texts.append(t)
        cur_topics.append(topic or "")
        cur_ids.append(cid)
        cur_len += len(t)
        if cur_len >= TARGET_CHARS:
            flush()
    flush()
    return passages, stats


# ── embed + store ────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i: i + EMBED_BATCH]
        client = _oai()
        resp = client.embeddings.create(model=_EMBED_MODEL, input=batch)
        out.extend(r.embedding for r in resp.data)
        print(f"    embedded {min(i + EMBED_BATCH, len(texts))}/{len(texts)}", flush=True)
    return out


def store(passages: list[dict], book: str, subject: str):
    conn = _db()
    inserted = 0
    for i in range(0, len(passages), DB_BATCH):
        batch = passages[i: i + DB_BATCH]
        for attempt in range(2):
            try:
                with conn.cursor() as cur:
                    cur.executemany(
                        """INSERT INTO book_passages
                           (book_name, subject, topic, passage_text, n_chunks, chunk_ids, embedding)
                           VALUES (%s,%s,%s,%s,%s,%s,%s::vector)""",
                        [
                            (book, subject, p["topic"], p["text"], p["n_chunks"],
                             p["chunk_ids"],
                             "[" + ",".join(str(x) for x in p["embedding"]) + "]")
                            for p in batch
                        ],
                    )
                conn.commit()
                break
            except psycopg2.OperationalError as e:
                print(f"    batch at {inserted} failed ({e}) — reconnecting...", flush=True)
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _db()
                if attempt == 1:
                    raise
        inserted += len(batch)
    conn.close()
    print(f"    stored {inserted} passages")


# ── main ─────────────────────────────────────────────────────────────────────

def build(only_book: str | None, wipe: bool, include_damaged: bool):
    conn = _db()
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT book_name, subject FROM book_chunks ORDER BY 1")
        books = cur.fetchall()
    conn.close()

    if only_book:
        books = [(b, s) for b, s in books if b == only_book]
        if not books:
            print(f"ERROR: book not found in book_chunks: {only_book}")
            sys.exit(1)

    skipped = [b for b, _ in books if b in DAMAGED_BOOKS and not include_damaged]
    if skipped:
        print(f"EXCLUDED (digit-corrupted, pending re-OCR): {skipped}")
        books = [(b, s) for b, s in books if b not in DAMAGED_BOOKS]

    if wipe:
        conn = _db()
        with conn.cursor() as cur:
            if only_book:
                cur.execute("DELETE FROM book_passages WHERE book_name = %s", (only_book,))
            else:
                cur.execute("TRUNCATE book_passages")
        conn.commit()
        conn.close()
        print("book_passages wiped." if not only_book else f"rows wiped for {only_book}.")

    grand = {"passages": 0, "junk_short": 0, "junk_repeat": 0,
             "junk_promo": 0, "junk_mcq": 0, "junk_toc": 0, "junk_bad_year": 0, "kept_chunks": 0}
    for book, subject in books:
        conn = _db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, topic, chunk_text FROM book_chunks WHERE book_name=%s ORDER BY id",
                (book,),
            )
            rows = cur.fetchall()
        conn.close()

        passages, stats = merge_book(rows)
        lens = [len(p["text"]) for p in passages] or [0]
        print(f"\n{book}  [{subject}]")
        print(f"  {len(rows)} chunks -> {len(passages)} passages "
              f"(avg {sum(lens)//len(lens)} chars) | junk dropped: "
              f"{stats['junk_short']} short + {stats['junk_repeat']} repeated-header "
              f"+ {stats['junk_promo']} promo + {stats['junk_mcq']} mcq-dump "
              f"+ {stats['junk_toc']} toc + {stats['junk_bad_year']} bad-year")

        embs = embed_texts([p["text"] for p in passages])
        for p, e in zip(passages, embs):
            p["embedding"] = e
        store(passages, book, subject)

        grand["passages"] += len(passages)
        for k in ("junk_short", "junk_repeat", "junk_promo", "junk_mcq",
                  "junk_toc", "junk_bad_year", "kept_chunks"):
            grand[k] += stats[k]

    dropped = (grand['junk_short'] + grand['junk_repeat'] + grand['junk_promo']
               + grand['junk_mcq'] + grand['junk_toc'] + grand['junk_bad_year'])
    print(f"\nDONE: {grand['passages']} passages from {grand['kept_chunks']} chunks "
          f"({dropped} junk chunks dropped: {grand['junk_short']} short, "
          f"{grand['junk_repeat']} header, {grand['junk_promo']} promo, "
          f"{grand['junk_mcq']} mcq-dump, {grand['junk_toc']} toc, {grand['junk_bad_year']} bad-year).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Merge book_chunks into book_passages.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="all books")
    g.add_argument("--book", help="one book_name")
    ap.add_argument("--wipe", action="store_true", help="delete existing passages first")
    ap.add_argument("--include-damaged", action="store_true",
                    help="also build the digit-corrupted books (after their re-OCR)")
    args = ap.parse_args()
    build(args.book, args.wipe, args.include_damaged)
