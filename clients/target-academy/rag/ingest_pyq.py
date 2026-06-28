# -*- coding: utf-8 -*-
"""
PYQ ingestion — markdown exam papers → pyq_chunks table.

Reads .md files from corpus/pyq/<exam-type>/, parses them question by question,
classifies each question's subject using Haiku (uk-history, uk-geography, etc.),
embeds with text-embedding-3-small, and stores in pyq_chunks.

Folder structure:
    corpus/pyq/
    ├── lekhpal-patwari/   ← exam type (mixed subjects per paper)
    ├── vdo-vpdo/
    └── group-c/

The exam-type folder name is stored in source_file for traceability.
The subject column is per-question (classified by Haiku), not per-file.

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
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
import anthropic

BASE    = Path(__file__).resolve().parents[1]
PYQ_DIR = BASE / "corpus" / "pyq"

EMBED_MODEL    = "text-embedding-3-small"
CLASSIFY_MODEL = "claude-haiku-4-5-20251001"
EMBED_BATCH    = 64
DB_BATCH       = 50

VALID_SUBJECTS = {
    "uk-history", "uk-geography", "uk-culture",
    "uk-general-studies", "general-gk", "hindi",
}

# Per-question subject classification. Haiku is cheap (~$0.0003 per 1k tokens).
# 100 questions × ~150 tokens each ≈ $0.005 per paper — negligible.
CLASSIFY_PROMPT = """Classify this Indian competitive exam question by subject.
Return ONLY one of these exact codes — no explanation, no punctuation:

uk-history        → Uttarakhand history, events, personalities, movements
uk-geography      → Uttarakhand geography, rivers, peaks, districts, climate
uk-culture        → Uttarakhand folk art, dance, music, festivals, traditions
uk-general-studies → Uttarakhand polity, governance, schemes, current affairs, economy
general-gk        → national GK, Indian polity/history, science, maths, reasoning, computer
hindi             → Hindi grammar, literature, vocabulary, sentence correction

Question:
{question}"""


# ── env + clients ─────────────────────────────────────────────────────────────

def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return

_load_env()
_oai_client: OpenAI | None = None
_claude_client: anthropic.Anthropic | None = None


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


def _db():
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set in .env")
    return psycopg2.connect(url, connect_timeout=30)


# ── markdown parsing ──────────────────────────────────────────────────────────

# Matches answer disclosure lines in various forms:
#   "Answer – (B)"  "Answer: B"  "Show Answer/Hide\nAnswer – (C)"
_ANSWER_LINE = re.compile(
    r"(?:Show Answer/Hide\s*)?Answer\s*[–\-:]\s*[\(\[]?([A-Da-d])[\)\]]?",
    re.IGNORECASE,
)

# MCQ options always start with (A), (B), (C), (D) — used to anchor question blocks.
_OPTION_LINE = re.compile(r"^\s*\([A-Da-d]\)\s+\S", re.MULTILINE)


def _find_question_starts(md_text: str) -> list[tuple[int, int]]:
    """Return (char_pos, question_number) for each real question boundary.

    A real question boundary is a line like "42. <text>" where the number is
    strictly one more than the previous found number (sequential). This filters
    out sub-item numbers inside matching/table questions (सूची-I items numbered
    1, 2, 3, 4 that reset and repeat inside the paper).
    """
    candidate = re.compile(r"^(\d{1,3})\.\s+\S", re.MULTILINE)
    results = []
    expected = 1
    for m in candidate.finditer(md_text):
        n = int(m.group(1))
        if n == expected:
            results.append((m.start(), n))
            expected += 1
        # allow one skip (occasional missing question in paper)
        elif n == expected + 1:
            results.append((m.start(), n))
            expected = n + 1
    return results


def parse_questions(md_text: str) -> list[dict]:
    """Split a markdown PYQ paper into individual question dicts.

    Returns: [{n, text, answer}]
      text   — stem + options, clean of answer/nav lines (this is what gets embedded)
      answer — correct letter a-d, or "" if not found
    """
    starts = _find_question_starts(md_text)
    if not starts:
        return []

    questions = []
    for i, (pos, n) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(md_text)
        block = md_text[pos:end].strip()

        ans_match = _ANSWER_LINE.search(block)
        answer = ans_match.group(1).lower() if ans_match else ""

        # strip answer + nav lines so they don't pollute the embedding
        clean = _ANSWER_LINE.sub("", block)
        clean = re.sub(r"Show Answer/Hide\s*", "", clean, flags=re.IGNORECASE)
        clean = clean.strip()

        if len(clean) < 20:  # skip stray header fragments
            continue

        questions.append({"n": n, "text": clean, "answer": answer})

    return questions


# ── subject classification ────────────────────────────────────────────────────

def classify_subjects(questions: list[dict]) -> list[str]:
    """Classify each question's subject with Haiku. Returns codes in same order."""
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
                    "content": CLASSIFY_PROMPT.format(question=q["text"][:600]),
                }],
            )
            code = msg.content[0].text.strip().lower().strip(".")
            subjects.append(code if code in VALID_SUBJECTS else "general-gk")
        except Exception as e:
            print(f"    Q{q['n']} classify error: {e} — defaulting to general-gk")
            subjects.append("general-gk")
    print(f"    {total}/{total} done.")
    return subjects


# ── embedding ─────────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i: i + EMBED_BATCH]
        resp = _oai().embeddings.create(model=EMBED_MODEL, input=batch)
        all_embeddings.extend([r.embedding for r in resp.data])
        print(f"    embedded {min(i + EMBED_BATCH, len(texts))}/{len(texts)}", flush=True)
    return all_embeddings


# ── already ingested? ─────────────────────────────────────────────────────────

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


# ── store ─────────────────────────────────────────────────────────────────────

def store_rows(rows: list[dict]):
    """rows: [{subject, source_file, chunk_text, embedding}]"""
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


# ── per-file ingestion ────────────────────────────────────────────────────────

def ingest_file(md_path: Path, dry_run: bool = False):
    source_file = md_path.name
    exam_type   = md_path.parent.name

    print(f"\n{'='*60}")
    print(f"File     : {source_file}")
    print(f"Exam type: {exam_type}")
    print(f"{'='*60}")

    if not dry_run and _already_ingested(source_file):
        print("  Already in DB — skipping.")
        return

    text = md_path.read_text(encoding="utf-8")
    questions = parse_questions(text)
    print(f"  Parsed {len(questions)} questions.")

    if not questions:
        print("  No questions found — check markdown format.")
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


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest PYQ markdown papers into pyq_chunks."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--exam", metavar="EXAM_TYPE",
        help="Exam folder to ingest: vdo-vpdo | lekhpal-patwari | group-c",
    )
    group.add_argument("--all", action="store_true", help="Ingest all exam folders")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse + classify only — no embeddings, no DB writes",
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
        md_files = sorted(exam_dir.glob("*.md"))
        if not md_files:
            print(f"No .md files in {exam_dir.name} — skipping.")
            continue
        for md_file in md_files:
            ingest_file(md_file, dry_run=args.dry_run)

    print("\nAll done.")
