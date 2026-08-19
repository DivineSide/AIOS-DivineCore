# -*- coding: utf-8 -*-
"""
reembed_e5.py — one-time LOCAL job: re-embed book_passages/pyq_chunks into
the parallel multilingual-e5-base tables (book_passages_e5/pyq_chunks_e5,
see migrations/006_e5_parallel_tables.sql).

Same pattern as reembed_bge.py: reads SOURCE TEXT unchanged (no AI
restructuring), embeds locally via sentence-transformers, writes to the
_e5 tables with source_id provenance. Original tables never touched.

e5-base requires "query: "/"passage: " prefixes on input text (per the
model's card — it was trained with this convention baked in; omitting it
measurably hurts retrieval quality). All corpus text is stored/retrieved as
a PASSAGE, so passage_text/chunk_text get the "passage: " prefix here.
Query-side embedding (at generation time) must use "query: " — that's
query.py's job when/if the e5 provider path is wired in.

Usage:
    python reembed_e5.py --all
    python reembed_e5.py --table book_passages
    python reembed_e5.py --table pyq_chunks
    python reembed_e5.py --all --wipe
"""

import argparse
import os
import time
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
EMBED_MODEL = "intfloat/multilingual-e5-base"
PASSAGE_PREFIX = "passage: "
BATCH_SIZE = 32          # encode() batch — CPU-bound, fast regardless of size
# INSERT batch — measured live: Supabase round-trip here has ~0.7s fixed
# latency per call, so committing every 32-row encode batch (the BGE-M3
# script's approach) meant ~9s per insert -> 0.6 rows/s -> ~9.5hr projected
# for the full corpus. Accumulating ~500 rows before each insert amortizes
# that fixed cost: measured ~23 rows/s, ~14 min for the full 19k-row table.
DB_BATCH = 500


def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return
    raise RuntimeError("no .env found")


def _db():
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set in .env")
    return psycopg2.connect(url, connect_timeout=15)


def _model():
    print("Loading multilingual-e5-base (cached locally already)...", flush=True)
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(EMBED_MODEL)
    print("Model loaded.", flush=True)
    return m


def _already_done_ids(conn, target_table: str) -> set[int]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT source_id FROM {target_table} WHERE source_id IS NOT NULL")
        return {r[0] for r in cur.fetchall()}


def reembed_book_passages(model, wipe: bool):
    conn = _db()
    if wipe:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE book_passages_e5")
        conn.commit()
        print("book_passages_e5 wiped.")

    done_ids = _already_done_ids(conn, "book_passages_e5")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, book_name, subject, topic, passage_text, n_chunks, chunk_ids
            FROM book_passages ORDER BY id
        """)
        rows = cur.fetchall()
    rows = [r for r in rows if r[0] not in done_ids]
    print(f"book_passages: {len(rows)} rows to embed (skipping {len(done_ids)} already done)")

    t0 = time.time()
    pending: list = []
    done = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        texts = [PASSAGE_PREFIX + r[4] for r in batch]
        embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        pending.extend(
            (r[0], r[1], r[2], r[3], r[4], r[5], r[6],
             "[" + ",".join(str(x) for x in e) + "]")
            for r, e in zip(batch, embs)
        )
        if len(pending) >= DB_BATCH or i + BATCH_SIZE >= len(rows):
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO book_passages_e5
                       (source_id, book_name, subject, topic, passage_text, n_chunks, chunk_ids, embedding)
                       VALUES %s""",
                    pending,
                    template="(%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                    page_size=len(pending),
                )
            conn.commit()
            done += len(pending)
            pending = []
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta_min = (len(rows) - done) / rate / 60 if rate > 0 else float("inf")
            print(f"  book_passages: {done}/{len(rows)}  "
                  f"({rate:.1f} rows/s, ETA {eta_min:.1f} min)", flush=True)
    conn.close()
    print(f"book_passages DONE in {(time.time()-t0)/60:.1f} min")


def reembed_pyq_chunks(model, wipe: bool):
    conn = _db()
    if wipe:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE pyq_chunks_e5")
        conn.commit()
        print("pyq_chunks_e5 wiped.")

    done_ids = _already_done_ids(conn, "pyq_chunks_e5")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, subject, source_file, chunk_text, answer, format, exam
            FROM pyq_chunks ORDER BY id
        """)
        rows = cur.fetchall()
    rows = [r for r in rows if r[0] not in done_ids]
    print(f"pyq_chunks: {len(rows)} rows to embed (skipping {len(done_ids)} already done)")

    t0 = time.time()
    pending: list = []
    done = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        texts = [PASSAGE_PREFIX + r[3] for r in batch]
        embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        pending.extend(
            (r[0], r[1], r[2], r[3],
             "[" + ",".join(str(x) for x in e) + "]", r[4], r[5], r[6])
            for r, e in zip(batch, embs)
        )
        if len(pending) >= DB_BATCH or i + BATCH_SIZE >= len(rows):
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO pyq_chunks_e5
                       (source_id, subject, source_file, chunk_text, embedding, answer, format, exam)
                       VALUES %s""",
                    pending,
                    template="(%s,%s,%s,%s,%s::vector,%s,%s,%s)",
                    page_size=len(pending),
                )
            conn.commit()
            done += len(pending)
            pending = []
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta_min = (len(rows) - done) / rate / 60 if rate > 0 else float("inf")
            print(f"  pyq_chunks: {done}/{len(rows)}  "
                  f"({rate:.1f} rows/s, ETA {eta_min:.1f} min)", flush=True)
    conn.close()
    print(f"pyq_chunks DONE in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    _load_env()
    ap = argparse.ArgumentParser(description="One-time local re-embed into multilingual-e5-base parallel tables.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--table", choices=["book_passages", "pyq_chunks"])
    ap.add_argument("--wipe", action="store_true", help="truncate the target _e5 table(s) first")
    args = ap.parse_args()

    model = _model()
    if args.all or args.table == "book_passages":
        reembed_book_passages(model, args.wipe)
    if args.all or args.table == "pyq_chunks":
        reembed_pyq_chunks(model, args.wipe)
    print("ALL DONE.")
