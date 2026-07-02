# -*- coding: utf-8 -*-
"""
PYQ ingestion — PDF exam papers → pyq_chunks table via Sarvam Vision.

Reads PDF files from corpus/pyq/<exam-type>/, splits them into <=10-page
chunks (Sarvam's document-digitization job cap), runs each chunk through the
Sarvam Vision document-intelligence API to get Markdown, parses the Markdown
into individual questions, classifies each question's subject using Haiku,
embeds with text-embedding-3-small, and stores in pyq_chunks.

Why not sarvam-105b: that model is text-only (confirmed via a live 400 —
"content must be a valid string"). Vision/OCR lives on a completely separate
model, "sarvam-vision", exposed via the document-intelligence batch-job API
(create_job -> upload_file -> start -> wait_until_complete -> download_output),
not the chat-completions endpoint.

These UKSSSC/UKPSC papers are bilingual: each question appears twice, once as
an English block and once as a Hindi block (numbering resets/duplicates across
the two halves — NOT one clean 1..N sequence). We keep only the Hindi blocks
(English terms embedded inside a Hindi question, e.g. 'Bharat Stage Standards',
are left alone — only whole blocks that are majority-Latin-script get dropped).

Folder structure:
    corpus/pyq/
    ├── lekhpal-patwari/
    ├── vdo-vpdo/
    └── group-c/

Usage:
    # ingest one exam folder
    python ingest_pyq.py --exam vdo-vpdo

    # ingest all exam folders
    python ingest_pyq.py --all

    # parse + classify only, no DB writes (check output before committing)
    python ingest_pyq.py --exam group-c --dry-run
"""

import io
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
import anthropic
import fitz  # PyMuPDF
from sarvamai import SarvamAI

BASE    = Path(__file__).resolve().parents[1]
PYQ_DIR = BASE / "corpus" / "pyq"

EMBED_MODEL      = "text-embedding-3-small"
CLASSIFY_MODEL   = "claude-haiku-4-5-20251001"
EMBED_BATCH      = 64
DB_BATCH         = 50
SARVAM_PAGE_CAP  = 10     # document-digitization job hard limit
HINDI_RATIO_MIN  = 0.4    # >=40% Devanagari-of-letters => treat block as Hindi

VALID_SUBJECTS = {
    "uk-history", "uk-geography", "uk-culture",
    "uk-general-studies", "general-gk", "hindi",
}

# ── env + clients ──────────────────────────────────────────────────────────────

def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return

_load_env()
_oai_client:    OpenAI | None              = None
_claude_client: anthropic.Anthropic | None = None
_sarvam_client: SarvamAI | None            = None


def _oai() -> OpenAI:
    global _oai_client
    if _oai_client is None:
        _oai_client = OpenAI(timeout=60, max_retries=3)
    return _oai_client


def _claude() -> anthropic.Anthropic:
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic()
    return _claude_client


def _sarvam() -> SarvamAI:
    global _sarvam_client
    if _sarvam_client is None:
        key = os.environ.get("SARVAM_API_KEY", "")
        if not key:
            raise RuntimeError("SARVAM_API_KEY not set in .env")
        _sarvam_client = SarvamAI(api_subscription_key=key)
    return _sarvam_client


def _db():
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set in .env")
    return psycopg2.connect(url, connect_timeout=30)


# ── PDF splitting (Sarvam caps a job at 10 pages) ───────────────────────────────

def split_pdf(pdf_path: Path, tmp_dir: Path, max_pages: int = SARVAM_PAGE_CAP) -> list[Path]:
    """Split a PDF into <=max_pages chunks. Returns paths to the chunk PDFs."""
    doc = fitz.open(str(pdf_path))
    total = doc.page_count
    chunk_paths = []
    for i, start in enumerate(range(0, total, max_pages)):
        end = min(start + max_pages, total) - 1
        chunk = fitz.open()
        chunk.insert_pdf(doc, from_page=start, to_page=end)
        out_path = tmp_dir / f"{pdf_path.stem}_part{i+1}.pdf"
        chunk.save(str(out_path))
        chunk.close()
        chunk_paths.append(out_path)
    doc.close()
    return chunk_paths


# ── Sarvam Vision document digitization ─────────────────────────────────────────

def digitize_pdf_chunk(pdf_path: Path) -> str:
    """Run one <=10-page PDF through Sarvam Vision. Returns the extracted Markdown."""
    job = _sarvam().document_intelligence.create_job(language="hi-IN", output_format="md")
    job.upload_file(str(pdf_path))
    job.start()
    status = job.wait_until_complete(poll_interval=3.0, timeout=300)

    if status.job_state != "Completed":
        raise RuntimeError(f"Sarvam job {job.job_id} ended in state {status.job_state}: {status.error_message}")

    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "output.zip"
        job.download_output(str(zip_path))
        with zipfile.ZipFile(zip_path) as zf:
            md_names = [n for n in zf.namelist() if n.endswith(".md")]
            if not md_names:
                raise RuntimeError(f"No .md file in Sarvam output for {pdf_path.name}")
            return zf.read(md_names[0]).decode("utf-8")


def digitize_pdf(pdf_path: Path) -> str:
    """Split (if needed) + digitize a full PDF. Returns concatenated Markdown."""
    with tempfile.TemporaryDirectory() as td:
        chunks = split_pdf(pdf_path, Path(td))
        print(f"  Split into {len(chunks)} chunk(s) of <= {SARVAM_PAGE_CAP} pages.")
        all_md = []
        for i, chunk_path in enumerate(chunks):
            print(f"  Digitizing chunk {i+1}/{len(chunks)} ({chunk_path.name})...", flush=True)
            try:
                md = digitize_pdf_chunk(chunk_path)
                all_md.append(md)
                print(f"    OK — {len(md)} chars extracted.")
            except Exception as e:
                print(f"    ERROR on chunk {i+1}: {e}")
        return "\n\n---\n\n".join(all_md)


# ── Markdown parsing (bilingual: keep Hindi blocks only) ────────────────────────

# MCQ question starts: "12. <text>" at the start of a line.
_QUESTION_START = re.compile(r"^(\d{1,3})\.\s+\S", re.MULTILINE)

# Devanagari Unicode block: U+0900–U+097F
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LETTER     = re.compile(r"[^\W\d_]", re.UNICODE)  # any alphabetic char, any script


def _devanagari_ratio(text: str) -> float:
    letters = _LETTER.findall(text)
    if not letters:
        return 0.0
    dev = sum(1 for c in letters if _DEVANAGARI.match(c))
    return dev / len(letters)


def parse_questions(md_text: str) -> list[dict]:
    """Split bilingual Sarvam-digitized Markdown into Hindi-only question dicts.

    The source has each question appearing twice — once in English, once in
    Hindi — with numbering that resets/duplicates across the two halves rather
    than forming one clean sequence. Strategy: find every "N. <text>" block
    regardless of order, classify each block's script by Devanagari ratio, keep
    only Hindi-majority blocks, and merge duplicate Hindi blocks for the same N
    (OCR sometimes splits one question across two fragments).
    """
    starts = [(m.start(), int(m.group(1))) for m in _QUESTION_START.finditer(md_text)]
    if not starts:
        return []

    blocks = []
    for i, (pos, n) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(md_text)
        text = md_text[pos:end].strip()
        if len(text) >= 15:
            blocks.append((n, text))

    hindi_by_n: dict[int, list[str]] = {}
    for n, text in blocks:
        if _devanagari_ratio(text) >= HINDI_RATIO_MIN:
            hindi_by_n.setdefault(n, []).append(text)

    questions = []
    for n in sorted(hindi_by_n):
        # merge fragments for the same question number (longest text wins if
        # duplicates look like near-repeats; otherwise concatenate fragments)
        fragments = hindi_by_n[n]
        if len(fragments) == 1:
            merged = fragments[0]
        else:
            fragments = sorted(set(fragments), key=len, reverse=True)
            merged = fragments[0]
        questions.append({"n": n, "text": merged})

    return questions


# ── subject classification ─────────────────────────────────────────────────────

_CLASSIFY_PROMPT = """Classify this Indian competitive exam question by subject.
Return ONLY one of these exact codes — no explanation, no punctuation:

uk-history        → Uttarakhand history, events, personalities, movements
uk-geography      → Uttarakhand geography, rivers, peaks, districts, climate
uk-culture        → Uttarakhand folk art, dance, music, festivals, traditions
uk-general-studies → Uttarakhand polity, governance, schemes, current affairs, economy
general-gk        → national GK, Indian polity/history, science, maths, reasoning, computer
hindi             → Hindi grammar, literature, vocabulary, sentence correction

Question:
{question}"""


def classify_subjects(questions: list[dict]) -> list[str]:
    subjects = []
    total = len(questions)
    print(f"  Classifying {total} questions with Haiku...")
    for i, q in enumerate(questions):
        if i % 25 == 0:
            print(f"    {i}/{total}...", flush=True)
        try:
            msg = _claude().messages.create(
                model=CLASSIFY_MODEL,
                max_tokens=20,
                messages=[{
                    "role": "user",
                    "content": _CLASSIFY_PROMPT.format(question=q["text"][:600]),
                }],
            )
            code = msg.content[0].text.strip().lower().strip(".")
            subjects.append(code if code in VALID_SUBJECTS else "general-gk")
        except Exception as e:
            print(f"    Q{q['n']} classify error: {e} — defaulting to general-gk")
            subjects.append("general-gk")
    print(f"    {total}/{total} done.")
    return subjects


# ── embedding ──────────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i: i + EMBED_BATCH]
        resp = _oai().embeddings.create(model=EMBED_MODEL, input=batch)
        all_embeddings.extend([r.embedding for r in resp.data])
        print(f"    embedded {min(i + EMBED_BATCH, len(texts))}/{len(texts)}", flush=True)
    return all_embeddings


# ── already ingested? ──────────────────────────────────────────────────────────

def _already_ingested(source_file: str) -> bool:
    try:
        conn = _db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM pyq_chunks WHERE source_file = %s",
                (source_file,),
            )
            count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


# ── store ──────────────────────────────────────────────────────────────────────

def store_rows(rows: list[dict]):
    conn = _db()
    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), DB_BATCH):
            batch = rows[i: i + DB_BATCH]
            cur.executemany(
                """INSERT INTO pyq_chunks (subject, source_file, chunk_text, embedding)
                   VALUES (%s, %s, %s, %s::vector)""",
                [
                    (
                        r["subject"],
                        r["source_file"],
                        r["chunk_text"],
                        "[" + ",".join(str(x) for x in r["embedding"]) + "]",
                    )
                    for r in batch
                ],
            )
            conn.commit()
            inserted += len(batch)
            print(f"    stored {inserted}/{len(rows)}", flush=True)
    conn.close()


# ── per-file ingestion ─────────────────────────────────────────────────────────

def ingest_file(pdf_path: Path, dry_run: bool = False):
    source_file = pdf_path.name

    print(f"\n{'='*60}")
    print(f"File     : {source_file}")
    print(f"Exam type: {pdf_path.parent.name}")
    print(f"{'='*60}")

    if not dry_run and _already_ingested(source_file):
        print("  Already in DB — skipping.")
        return

    md_text = digitize_pdf(pdf_path)
    questions = parse_questions(md_text)
    print(f"  Parsed {len(questions)} Hindi questions.")

    if not questions:
        print("  No questions found — check PDF/Markdown quality.")
        return

    subjects = classify_subjects(questions)
    dist = Counter(subjects)
    print(f"  Subject distribution: {dict(dist)}")

    if dry_run:
        print("  DRY RUN — skipping embed + store.")
        for q, s in list(zip(questions, subjects))[:5]:
            print(f"    Q{q['n']} [{s}]: {q['text'][:100]}...")
        return

    print(f"  Embedding {len(questions)} questions...")
    embeddings = embed_texts([q["text"] for q in questions])

    rows = [
        {
            "subject":    subjects[i],
            "source_file": source_file,
            "chunk_text": questions[i]["text"],
            "embedding":  embeddings[i],
        }
        for i in range(len(questions))
    ]

    store_rows(rows)
    print(f"  DONE: {len(rows)} chunks stored for '{source_file}'")


# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest PYQ PDF papers into pyq_chunks via Sarvam Vision."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--exam", metavar="EXAM_TYPE",
        help="Exam folder to ingest: vdo-vpdo | lekhpal-patwari | group-c",
    )
    group.add_argument("--all", action="store_true", help="Ingest all exam folders")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Extract + classify only — no embeddings, no DB writes",
    )
    args = parser.parse_args()

    if args.all:
        exam_dirs = sorted(d for d in PYQ_DIR.iterdir() if d.is_dir())
    else:
        exam_dirs = [PYQ_DIR / args.exam]

    for exam_dir in exam_dirs:
        if not exam_dir.exists():
            print(f"ERROR: folder not found: {exam_dir}")
            sys.exit(1)
        pdf_files = sorted(f for f in exam_dir.glob("*.pdf") if not f.name.startswith("."))
        if not pdf_files:
            print(f"No .pdf files in {exam_dir.name} — skipping.")
            continue
        for pdf_file in pdf_files:
            ingest_file(pdf_file, dry_run=args.dry_run)

    print("\nAll done.")
