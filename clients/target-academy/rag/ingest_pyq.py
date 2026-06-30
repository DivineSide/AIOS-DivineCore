# -*- coding: utf-8 -*-
"""
PYQ ingestion — PDF exam papers → pyq_chunks table via Sarvam vision.

Reads PDF files from corpus/pyq/<exam-type>/, renders each page to an image,
sends pages to Sarvam-105b (vision) to extract questions as structured JSON,
classifies each question's subject using Haiku, embeds with text-embedding-3-small,
and stores in pyq_chunks.

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

import base64
import io
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
import anthropic
import fitz  # PyMuPDF

BASE    = Path(__file__).resolve().parents[1]
PYQ_DIR = BASE / "corpus" / "pyq"

EMBED_MODEL    = "text-embedding-3-small"
CLASSIFY_MODEL = "claude-haiku-4-5-20251001"
SARVAM_MODEL   = "sarvam-105b"
PAGE_DPI       = 150   # render resolution — 150dpi is sharp enough for Hindi text
EMBED_BATCH    = 64
DB_BATCH       = 50
PAGES_PER_CALL = 2     # pages per Sarvam vision call (stays under token cap)

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
_oai_client:    OpenAI | None             = None
_claude_client: anthropic.Anthropic | None = None
_sarvam_client: OpenAI | None             = None   # OpenAI-compat, Sarvam base


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


def _sarvam() -> OpenAI:
    global _sarvam_client
    if _sarvam_client is None:
        key = os.environ.get("SARVAM_API_KEY", "")
        if not key:
            raise RuntimeError("SARVAM_API_KEY not set in .env")
        _sarvam_client = OpenAI(
            api_key=key,
            base_url="https://api.sarvam.ai/v1",
            timeout=120,
            max_retries=2,
        )
    return _sarvam_client


def _db():
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set in .env")
    return psycopg2.connect(url, connect_timeout=30)


# ── PDF → images ───────────────────────────────────────────────────────────────

def pdf_to_page_images(pdf_path: Path, dpi: int = PAGE_DPI) -> list[bytes]:
    """Render each page of a PDF to PNG bytes."""
    doc = fitz.open(str(pdf_path))
    zoom = dpi / 72.0
    mat  = fitz.Matrix(zoom, zoom)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        images.append(pix.tobytes("png"))
    doc.close()
    return images


def _b64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode()


# ── Sarvam vision extraction ───────────────────────────────────────────────────

_EXTRACT_SYSTEM = """\
You are an expert Hindi exam paper transcriber for Indian state PSC/SSC exams.
You will be given one or more pages from an exam paper (UKSSSC / UKPSC / similar).

Extract every MCQ question you can see and return a JSON array with this shape:
[
  {
    "n": <integer question number>,
    "text": "<question stem + all options in Devanagari, exactly as printed>"
  },
  ...
]

Rules:
- Transcribe Hindi Devanagari EXACTLY — no spelling correction, no translation.
- Include the question number and all four options (क/ख/ग/घ or A/B/C/D) in "text".
- Skip section headings, instructions, and non-MCQ content.
- If a page has no MCQ questions, return an empty array [].
- Return ONLY the JSON array, no prose, no markdown fences.
"""


def _extract_questions_from_pages(page_images: list[bytes], start_page: int) -> list[dict]:
    """Send a batch of page images to Sarvam vision → [{n, text}]."""
    content = []
    for i, png in enumerate(page_images):
        content.append({
            "type": "text",
            "text": f"Page {start_page + i + 1}:",
        })
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{_b64(png)}"},
        })
    content.append({
        "type": "text",
        "text": "Extract all MCQ questions from these pages and return a JSON array.",
    })

    resp = _sarvam().chat.completions.create(
        model=SARVAM_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user",   "content": content},
        ],
    )
    raw = resp.choices[0].message.content.strip()

    # strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # try to pull the array out of surrounding text
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    print(f"    WARNING: could not parse JSON from pages {start_page+1}-{start_page+len(page_images)}")
    return []


def extract_questions_from_pdf(pdf_path: Path) -> list[dict]:
    """Full extraction: render PDF → call Sarvam in page batches → deduplicated list."""
    print(f"  Rendering PDF to images ({PAGE_DPI}dpi)...")
    page_images = pdf_to_page_images(pdf_path)
    total_pages = len(page_images)
    print(f"  {total_pages} pages rendered.")

    all_questions: dict[int, dict] = {}  # keyed by n to deduplicate
    for i in range(0, total_pages, PAGES_PER_CALL):
        batch = page_images[i: i + PAGES_PER_CALL]
        print(f"  Calling Sarvam vision: pages {i+1}-{i+len(batch)} of {total_pages}...", flush=True)
        try:
            questions = _extract_questions_from_pages(batch, start_page=i)
            new = 0
            for q in questions:
                n = int(q.get("n", 0))
                text = str(q.get("text", "")).strip()
                if n > 0 and len(text) > 10 and n not in all_questions:
                    all_questions[n] = {"n": n, "text": text}
                    new += 1
            print(f"    → {new} new questions (total so far: {len(all_questions)})")
        except Exception as e:
            print(f"    ERROR on pages {i+1}-{i+len(batch)}: {e}")

    # return sorted by question number
    return [all_questions[n] for n in sorted(all_questions)]


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

    questions = extract_questions_from_pdf(pdf_path)
    print(f"  Extracted {len(questions)} questions.")

    if not questions:
        print("  No questions found — check PDF quality.")
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
        description="Ingest PYQ PDF papers into pyq_chunks via Sarvam vision."
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
