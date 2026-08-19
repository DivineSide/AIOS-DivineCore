# -*- coding: utf-8 -*-
"""
reembed_bge.py — one-time LOCAL job: re-embed book_passages/pyq_chunks into
the parallel BGE-M3 tables (book_passages_bge/pyq_chunks_bge, see
migrations/005_bge_parallel_tables.sql).

WHY LOCAL, NOT ON THE SERVER: BGE-M3 (~2.3GB, needs ~1.8GB+ RAM headroom at
inference) does not fit on the Hetzner CX23 VPS alongside the existing
Docker stack — confirmed via a live OOM-killed test (2026-07-25, exit 137
even with only the existing containers' baseline usage). This script reads
the SOURCE TEXT (passage_text/chunk_text — unchanged, no AI restructuring,
no re-segmentation) from Supabase, embeds it locally with BGE-M3 via
sentence-transformers (CPU, works fine for this one-time bulk job), and
writes into the *_bge tables. The original book_passages/pyq_chunks tables
are never touched by this script — reads only.

Usage:
    python reembed_bge.py --all                # both tables
    python reembed_bge.py --table book_passages
    python reembed_bge.py --table pyq_chunks
    python reembed_bge.py --all --wipe          # clear *_bge tables first (re-run from scratch)
"""

import argparse
import os
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
EMBED_MODEL = "BAAI/bge-m3"
BATCH_SIZE = 32          # passages per encode() call — CPU-friendly batch
DB_BATCH = 200           # rows per INSERT batch


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
    print("Loading BGE-M3 (first run downloads ~2.3GB, cached after)...", flush=True)
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(EMBED_MODEL)
    print("Model loaded.", flush=True)
    return m


def _already_done_ids(conn, target_table: str) -> set[int]:
    """source_ids already present in the _bge table — lets a partial/interrupted
    run resume without re-embedding rows it already finished."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT source_id FROM {target_table} WHERE source_id IS NOT NULL")
        return {r[0] for r in cur.fetchall()}


def reembed_book_passages(model, wipe: bool):
    conn = _db()
    if wipe:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE book_passages_bge")
        conn.commit()
        print("book_passages_bge wiped.")

    done_ids = _already_done_ids(conn, "book_passages_bge")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, book_name, subject, topic, passage_text, n_chunks, chunk_ids
            FROM book_passages ORDER BY id
        """)
        rows = cur.fetchall()
    rows = [r for r in rows if r[0] not in done_ids]
    print(f"book_passages: {len(rows)} rows to embed (skipping {len(done_ids)} already done)")

    t0 = time.time()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        texts = [r[4] for r in batch]
        embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO book_passages_bge
                   (source_id, book_name, subject, topic, passage_text, n_chunks, chunk_ids, embedding)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)""",
                [
                    (r[0], r[1], r[2], r[3], r[4], r[5], r[6],
                     "[" + ",".join(str(x) for x in e) + "]")
                    for r, e in zip(batch, embs)
                ],
            )
        conn.commit()
        done = min(i + BATCH_SIZE, len(rows))
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
            cur.execute("TRUNCATE pyq_chunks_bge")
        conn.commit()
        print("pyq_chunks_bge wiped.")

    done_ids = _already_done_ids(conn, "pyq_chunks_bge")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, subject, source_file, chunk_text, answer, format, exam
            FROM pyq_chunks ORDER BY id
        """)
        rows = cur.fetchall()
    rows = [r for r in rows if r[0] not in done_ids]
    print(f"pyq_chunks: {len(rows)} rows to embed (skipping {len(done_ids)} already done)")

    t0 = time.time()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        texts = [r[3] for r in batch]
        embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO pyq_chunks_bge
                   (source_id, subject, source_file, chunk_text, embedding, answer, format, exam)
                   VALUES (%s,%s,%s,%s,%s::vector,%s,%s,%s)""",
                [
                    (r[0], r[1], r[2], r[3],
                     "[" + ",".join(str(x) for x in e) + "]", r[4], r[5], r[6])
                    for r, e in zip(batch, embs)
                ],
            )
        conn.commit()
        done = min(i + BATCH_SIZE, len(rows))
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta_min = (len(rows) - done) / rate / 60 if rate > 0 else float("inf")
        print(f"  pyq_chunks: {done}/{len(rows)}  "
              f"({rate:.1f} rows/s, ETA {eta_min:.1f} min)", flush=True)
    conn.close()
    print(f"pyq_chunks DONE in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    _load_env()
    ap = argparse.ArgumentParser(description="One-time local re-embed into BGE-M3 parallel tables.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--table", choices=["book_passages", "pyq_chunks"])
    ap.add_argument("--wipe", action="store_true", help="truncate the target _bge table(s) first")
    args = ap.parse_args()

    model = _model()
    if args.all or args.table == "book_passages":
        reembed_book_passages(model, args.wipe)
    if args.all or args.table == "pyq_chunks":
        reembed_pyq_chunks(model, args.wipe)
    print("ALL DONE.")
