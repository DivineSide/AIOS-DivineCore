# -*- coding: utf-8 -*-
"""
RAG ingestion pipeline — PDF → OCR/extract → topic-chunk → embed → Supabase.

Usage:
    python ingest.py --book "hindi/KIRAN सामान्य हिन्दी.pdf"
    python ingest.py --book "uk-history/uttarakhand_ka_itihas_sushil_jardhari.pdf"

Books live in: clients/target-academy/corpus/book-sources/<subject>/<file>.pdf
The --book argument is relative to that folder (can include subfolder).
"""

import io
import sys
import os
import json
import concurrent.futures
from pathlib import Path

# UTF-8 stdout for Devanagari on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)

import psycopg2
import pymupdf as fitz
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI
import pytesseract

BASE        = Path(__file__).resolve().parents[1]
BOOKS_DIR   = BASE / "corpus" / "book-sources"
CHECKPOINT  = Path(__file__).resolve().parent / ".checkpoints"
CHECKPOINT.mkdir(exist_ok=True)

EMBED_MODEL  = "text-embedding-3-small"
SEGMENT_MODEL = "gpt-4o-mini"
CHUNK_CHARS  = 8000
BATCH_CHARS  = 80_000
BATCH_CHUNKS = 64
DB_BATCH     = 50

# ---------------------------------------------------------------------------
# env + clients
# ---------------------------------------------------------------------------
def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return

_load_env()
_openai: OpenAI | None = None

def _oai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(timeout=90, max_retries=5)
    return _openai

def _db():
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set in .env")
    return psycopg2.connect(url, connect_timeout=30)

# ---------------------------------------------------------------------------
# already ingested?
# ---------------------------------------------------------------------------
def _already_ingested(book_name: str) -> bool:
    try:
        conn = _db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM book_chunks WHERE book_name = %s", (book_name,))
            count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False

# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------
def ocr_page(img):
    return pytesseract.image_to_string(img, lang="hin")

def extract_text_scanned(path: Path) -> str:
    doc = fitz.open(str(path))
    total = len(doc)
    parts = []
    skipped = 0
    print(f"  OCR ({total} pages)...")
    for i, page in enumerate(doc):
        if i % 10 == 0 or i == total - 1:
            pct = int((i + 1) / total * 100)
            bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
            print(f"    [{bar}] {pct}% page {i+1}/{total} (skipped {skipped})", flush=True)
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(ocr_page, img)
                text = future.result(timeout=30)
            if text.strip():
                parts.append(text.strip())
        except concurrent.futures.TimeoutError:
            skipped += 1
    return "\n\n".join(parts)

def extract_text_digital(path: Path) -> str:
    doc = fitz.open(str(path))
    parts = []
    for page in doc:
        t = page.get_text()
        if t.strip():
            parts.append(t.strip())
    return "\n\n".join(parts)

def has_text_layer(path: Path) -> bool:
    doc = fitz.open(str(path))
    for i, page in enumerate(doc):
        if i >= 5:
            break
        if len(page.get_text().strip()) > 100:
            return True
    return False

def extract_text(path: Path) -> str:
    if has_text_layer(path):
        print("  Digital PDF detected — extracting text layer...")
        return extract_text_digital(path)
    else:
        print("  Scanned PDF detected — running Tesseract OCR...")
        return extract_text_scanned(path)

# ---------------------------------------------------------------------------
# topic-aware segmentation
# ---------------------------------------------------------------------------
SEGMENT_PROMPT = """You are a Hindi/English text segmenter for an educational RAG system.
Split the following text into topic-coherent chunks. Each chunk should cover ONE topic or concept.
Return JSON: {"chunks": [{"topic": "...", "text": "..."}]}
Topics should be short (3-8 words). Text should be complete sentences only.
Do not truncate or summarize — preserve the original text exactly."""

def _segment_window(window: str) -> list[dict]:
    resp = _oai().chat.completions.create(
        model=SEGMENT_MODEL,
        messages=[
            {"role": "system", "content": SEGMENT_PROMPT},
            {"role": "user", "content": window},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    data = json.loads(resp.choices[0].message.content)
    return data.get("chunks", [])

def segment_text(text: str) -> list[dict]:
    windows = []
    for i in range(0, len(text), CHUNK_CHARS):
        w = text[i: i + CHUNK_CHARS]
        if w.strip():
            windows.append(w)

    total = len(windows)
    print(f"  Segmenting {total} windows (8 concurrent)...")
    results = [None] * total
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        future_to_idx = {ex.submit(_segment_window, w): i for i, w in enumerate(windows)}
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                print(f"    window {idx} failed: {e}")
                results[idx] = []
            completed += 1
            print(f"    window {completed}/{total} done", flush=True)

    chunks = []
    for r in results:
        if r:
            chunks.extend(r)
    return chunks

# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------
def embed_chunks(chunks: list[dict]) -> list[dict]:
    print(f"  Embedding {len(chunks)} chunks...")
    results = []
    batch_texts = []
    batch_items = []
    batch_chars = 0

    def flush(texts, items):
        if not texts:
            return
        resp = _oai().embeddings.create(model=EMBED_MODEL, input=texts)
        for item, emb in zip(items, resp.data):
            results.append({**item, "embedding": emb.embedding})
        print(f"    embedded {len(results)}/{len(chunks)}", flush=True)

    for chunk in chunks:
        t = chunk.get("text", "")
        if not t.strip():
            continue
        if batch_chars + len(t) > BATCH_CHARS or len(batch_items) >= BATCH_CHUNKS:
            flush(batch_texts, batch_items)
            batch_texts, batch_items, batch_chars = [], [], 0
        batch_texts.append(t)
        batch_items.append(chunk)
        batch_chars += len(t)

    flush(batch_texts, batch_items)
    return results

# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------
def store_chunks(chunks: list[dict], book_name: str, subject: str):
    print(f"  Storing {len(chunks)} rows in Supabase...")
    conn = _db()
    rows = []
    for c in chunks:
        vec = "[" + ",".join(str(x) for x in c["embedding"]) + "]"
        rows.append((book_name, subject, c.get("topic", ""), c.get("text", ""), vec))

    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), DB_BATCH):
            batch = rows[i: i + DB_BATCH]
            cur.executemany(
                "INSERT INTO book_chunks (book_name, subject, topic, chunk_text, embedding) VALUES (%s,%s,%s,%s,%s::vector)",
                batch,
            )
            conn.commit()
            inserted += len(batch)
            print(f"    inserted {inserted}/{len(rows)}", flush=True)
    conn.close()

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def ingest(book_arg: str):
    # book_arg can be "hindi/KIRAN.pdf" or just "KIRAN.pdf"
    book_path = BOOKS_DIR / book_arg
    if not book_path.exists():
        print(f"ERROR: file not found: {book_path}")
        sys.exit(1)

    book_name = book_path.name
    subject   = book_path.parent.name  # folder name = subject

    print(f"\n{'='*60}")
    print(f"Book   : {book_name}")
    print(f"Subject: {subject}")
    print(f"Path   : {book_path}")
    print(f"{'='*60}")

    if _already_ingested(book_name):
        print(f"  Already in DB — skipping.")
        return

    checkpoint = CHECKPOINT / f"{book_name}.chunks.json"

    if checkpoint.exists():
        print(f"  Checkpoint found — loading segments from disk...")
        with open(checkpoint, encoding="utf-8") as f:
            chunks = json.load(f)
        print(f"  Loaded {len(chunks)} chunks from checkpoint.")
    else:
        text = extract_text(book_path)
        if not text.strip():
            print("  ERROR: no text extracted.")
            return
        print(f"  Extracted {len(text):,} chars.")

        chunks = segment_text(text)
        print(f"  Segmented into {len(chunks)} chunks.")

        with open(checkpoint, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        print(f"  Checkpoint saved.")

    chunks_with_embeddings = embed_chunks(chunks)
    store_chunks(chunks_with_embeddings, book_name, subject)

    print(f"\n  DONE: {len(chunks_with_embeddings)} chunks ingested for '{book_name}'")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, help="Path relative to book-sources/, e.g. hindi/KIRAN.pdf")
    args = parser.parse_args()
    ingest(args.book)
