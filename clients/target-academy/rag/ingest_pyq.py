# -*- coding: utf-8 -*-
"""
PYQ ingestion — Previous-Year-Question PDFs -> one chunk per question -> embed
-> pyq_chunks table.

Unlike ingest.py (which topic-segments book content), PYQs are chunked BY QUESTION:
each question (stem + its options) becomes one row. These are used in Phase 1 of
the generate pipeline to infer what topics an exam tends to test — not as source
material — so we keep them whole and atomic, no LLM segmentation.

Usage:
    python ingest_pyq.py --pyq "uk-history/UKSSSC-2023.pdf"
    python ingest_pyq.py --pyq "general-gk/lucent-gk.pdf"

PYQ files live in: clients/target-academy/corpus/pyq/<subject>/<file>.pdf
The --pyq argument is relative to that folder (subject = first path segment).
"""
import io
import os
import re
import sys
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

BASE = Path(__file__).resolve().parents[1]
PYQ_DIR = BASE / "corpus" / "pyq"

EMBED_MODEL = "text-embedding-3-small"
BATCH_CHUNKS = 64
DB_BATCH = 50

# a question usually starts with a number marker: "1.", "१.", "Q1", "12)" etc.
QUESTION_START = re.compile(r"(?m)^\s*(?:Q\.?\s*)?[\(\[]?(?:\d{1,3}|[०-९]{1,3})[\.\)\]]\s+")


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


def _already_ingested(source_file: str) -> bool:
    try:
        conn = _db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pyq_chunks WHERE source_file = %s", (source_file,))
            count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


# ── PDF text extraction (same auto digital/scanned logic as ingest.py) ───────

def _has_text_layer(path: Path) -> bool:
    doc = fitz.open(str(path))
    for i, page in enumerate(doc):
        if i >= 5:
            break
        if len(page.get_text().strip()) > 100:
            return True
    return False


def _extract_digital(path: Path) -> str:
    doc = fitz.open(str(path))
    return "\n\n".join(p.get_text().strip() for p in doc if p.get_text().strip())


def _extract_scanned(path: Path) -> str:
    doc = fitz.open(str(path))
    parts = []
    print(f"  OCR ({len(doc)} pages)...")
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(img, lang="hin")
        if text.strip():
            parts.append(text.strip())
        if i % 10 == 0:
            print(f"    page {i+1}/{len(doc)}", flush=True)
    return "\n\n".join(parts)


def _extract_text(path: Path) -> str:
    if _has_text_layer(path):
        print("  Digital PDF — extracting text layer...")
        return _extract_digital(path)
    print("  Scanned PDF — running OCR...")
    return _extract_scanned(path)


# ── chunk by question ────────────────────────────────────────────────────────

def _split_questions(text: str) -> list[str]:
    """Split raw text into individual questions on the leading number marker.
    Falls back to blank-line paragraphs if no numbered markers are found."""
    matches = list(QUESTION_START.finditer(text))
    if len(matches) >= 3:
        questions = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            q = text[start:end].strip()
            if len(q) > 15:  # drop stray fragments
                questions.append(q)
        return questions
    # fallback: paragraphs separated by blank lines
    return [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 15]


def _embed_batch(texts: list[str]) -> list[list[float]]:
    resp = _oai().embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def _store(questions: list[str], source_file: str, subject: str):
    print(f"  Embedding + storing {len(questions)} questions...")
    conn = _db()
    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(questions), BATCH_CHUNKS):
            batch = questions[i: i + BATCH_CHUNKS]
            embeddings = _embed_batch(batch)
            rows = []
            for q, emb in zip(batch, embeddings):
                vec = "[" + ",".join(str(x) for x in emb) + "]"
                rows.append((subject, source_file, q, vec))
            cur.executemany(
                "INSERT INTO pyq_chunks (subject, source_file, chunk_text, embedding) "
                "VALUES (%s,%s,%s,%s::vector)",
                rows,
            )
            conn.commit()
            inserted += len(rows)
            print(f"    inserted {inserted}/{len(questions)}", flush=True)
    conn.close()


def ingest(pyq_arg: str):
    path = PYQ_DIR / pyq_arg
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    source_file = path.name
    subject = path.parent.name  # folder = subject (uk-history, general-gk, ...)

    print(f"\n{'='*60}\nPYQ    : {source_file}\nSubject: {subject}\n{'='*60}")

    if _already_ingested(source_file):
        print("  Already in DB — skipping.")
        return

    text = _extract_text(path)
    if not text.strip():
        print("  ERROR: no text extracted.")
        return
    print(f"  Extracted {len(text):,} chars.")

    questions = _split_questions(text)
    print(f"  Split into {len(questions)} questions.")
    if not questions:
        print("  ERROR: no questions found.")
        return

    _store(questions, source_file, subject)
    print(f"\n  DONE: {len(questions)} PYQs ingested for '{source_file}'")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyq", required=True, help="Path relative to corpus/pyq/, e.g. uk-history/UKSSSC-2023.pdf")
    args = parser.parse_args()
    ingest(args.pyq)
