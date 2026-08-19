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
    # ingest one exam folder (.md read directly; .pdf digitized via Sarvam)
    python ingest_pyq.py --exam vdo-vpdo

    # all folders, markdown sources only (zero Sarvam spend)
    python ingest_pyq.py --all --md-only --replace

    # parse only, no DB writes (check parse quality before committing)
    python ingest_pyq.py --all --md-only --dry-run

    # one file
    python ingest_pyq.py --file vdo-vpdo/vdo-vpdo-2023-07-09.md --replace
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
    "uk-general-studies", "general-gk", "hindi", "computer",
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


# ── Markdown parsing (answer-terminated segmentation) ───────────────────────────
#
# THE OLD PARSER'S FATAL FLAW: it treated every "N. <text>" line as a question
# start. But सुमेलित (match-the-following) questions internally contain numbered
# सूची-II items ("1. कपड़ा उद्योग"), so the parser CUT the question there —
# decapitating exactly the complex formats the client wants, and leaving stray
# fragments filed under wrong question numbers. Verified in the DB: 66-char
# सुमेलित stubs whose lists and कूट options are gone.
#
# THE FIX: don't guess where a question STARTS — key off where it ENDS. Every
# question in these source markdowns is terminated by an official answer line
# ("Answer – (C)" / "उत्तर – (B)", 762 across the 7 files). Segmenting on that
# terminator makes internal numbered lines structurally incapable of splitting a
# question. As a bonus the answer itself — thrown away for months — is captured.

# MCQ question starts: "12. <text>" at the start of a line.
_QUESTION_START = re.compile(r"^(\d{1,3})\.\s+\S", re.MULTILINE)

# The official answer terminator. Styles seen across the corpus:
#   "Answer – (C)"  "Answer- (D)"  "उत्तर – (B)"  "उत्तर (A)"  "Answer – (*)"
# (* = question cancelled/starred by the commission -> answer stays None)
_ANSWER_LINE = re.compile(
    r"^\s*(?:Answer|उत्तर)\s*[-–—:]*\s*\(?\s*([A-Ea-e*])\s*\)?\s*[.।]?\s*$")
# Web furniture from the source site — stripped wherever it appears.
_FURNITURE = re.compile(r"^\s*(Show Answer/Hide|Hide Answer|Show Answer)\s*$")
# An option line: "(A) ...", "(b) ...". Used to validate a segment really is an MCQ.
_OPTION_LINE = re.compile(r"^\s*\(\s*[A-Ea-e]\s*\)\s*\S")

# Devanagari Unicode block: U+0900–U+097F
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LETTER     = re.compile(r"[^\W\d_]", re.UNICODE)  # any alphabetic char, any script


def _devanagari_ratio(text: str) -> float:
    letters = _LETTER.findall(text)
    if not letters:
        return 0.0
    dev = sum(1 for c in letters if _DEVANAGARI.match(c))
    return dev / len(letters)


# Format tags — mechanical, marker-phrase based. Checked in priority order
# (a सुमेलित question may also contain कथन-ish words; match wins).
_FORMAT_RULES: list[tuple[str, re.Pattern]] = [
    ("figure",    re.compile(r"प्रश्न\s*आकृति|उत्तर\s*आकृति|आकृति\s+में|निम्न\s*आकृति")),
    ("match",     re.compile(r"सुमेलित|सूची\s*[-–—]?\s*I|कूट\s*[:：]")),
    ("assertion", re.compile(r"अभिकथन|कथन\s*\(\s*A\s*\)|कारण\s*\(\s*R\s*\)")),
    ("statement", re.compile(r"कथनों?\s+पर\s+विचार|निम्नलिखित\s+कथन|सही\s+कथन|असत्य\s+कथन|सत्य\s+कथन")),
    ("order",     re.compile(r"(सही|काला?नुक्रम|आरोही|अवरोही)\s*क्रम|क्रम\s+में\s+व्यवस्थित|कालक्रम")),
]


def detect_format(text: str) -> str:
    for tag, rx in _FORMAT_RULES:
        if rx.search(text):
            return tag
    return "plain"


def _clean_segment_lines(lines: list[str]) -> list[str]:
    """Strip web furniture and collapse blank runs, keep everything else verbatim."""
    out: list[str] = []
    for ln in lines:
        if _FURNITURE.match(ln):
            continue
        if not ln.strip() and out and not out[-1].strip():
            continue  # collapse multiple blanks
        out.append(ln.rstrip())
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def _question_from_segment(lines: list[str]) -> dict | None:
    """One answer-terminated segment -> {n, text} or None if it's furniture.

    The segment may carry leading page furniture (site preamble, page headers,
    a bilingual English duplicate). The question proper starts at the EARLIEST
    "N. <text>" line whose remainder-block is Hindi-majority and contains at
    least 2 option lines — सूची-II items never win because the real question
    start always precedes them."""
    starts = [i for i, ln in enumerate(lines) if _QUESTION_START.match(ln)]
    for i in starts:
        block = lines[i:]
        n_options = sum(1 for ln in block if _OPTION_LINE.match(ln))
        text = "\n".join(_clean_segment_lines(block))
        if n_options >= 2 and _devanagari_ratio(text) >= HINDI_RATIO_MIN and len(text) >= 30:
            n = int(_QUESTION_START.match(lines[i]).group(1))
            return {"n": n, "text": text}
    return None


def parse_questions(md_text: str) -> list[dict]:
    """Split source Markdown into question dicts: {n, text, answer, format}.

    Primary strategy — ANSWER-TERMINATED segmentation: a question is everything
    since the previous "Answer – (X)" line up to (not including) the next one.
    Numbered list items INSIDE a question can never split it, because segment
    boundaries are answer lines, not numbered lines. Trailing page furniture
    after the last answer is dropped automatically (no terminator = no segment).

    Fallback — for sources with no answer lines at all (some future PDF
    digitizations), fall back to numbered-start segmentation, but a new start
    only counts once the current block already holds a complete (A)-(D) options
    run, which is what protects सुमेलित list items in that mode."""
    all_lines = md_text.splitlines()
    answer_idx = [(i, m.group(1)) for i, ln in enumerate(all_lines)
                  if (m := _ANSWER_LINE.match(ln))]

    questions: list[dict] = []

    if len(answer_idx) >= 5:  # answer-keyed source (all current markdowns)
        prev = 0
        for i, letter in answer_idx:
            q = _question_from_segment(all_lines[prev:i])
            if q is not None:
                letter = letter.lower()
                q["answer"] = letter if letter in "abcde" else None
                q["format"] = detect_format(q["text"])
                questions.append(q)
            prev = i + 1
        return questions

    # ── fallback: no answer key in source ──
    blocks: list[list[str]] = []
    cur: list[str] = []
    for ln in all_lines:
        if _QUESTION_START.match(ln) and cur:
            # only a COMPLETE block (>=4 option lines) can be closed by a new start;
            # otherwise this numbered line is an internal item (सूची-II, कथन list)
            if sum(1 for l in cur if _OPTION_LINE.match(l)) >= 4:
                blocks.append(cur)
                cur = []
        cur.append(ln)
    if cur:
        blocks.append(cur)
    for block in blocks:
        q = _question_from_segment(block)
        if q is not None:
            q["answer"] = None
            q["format"] = detect_format(q["text"])
            questions.append(q)
    return questions


# ── subject classification ─────────────────────────────────────────────────────

_CLASSIFY_PROMPT = """Classify this Indian competitive exam question by subject.
Return ONLY one of these exact codes — no explanation, no punctuation:

uk-history        → Uttarakhand history, events, personalities, movements
uk-geography      → Uttarakhand geography, rivers, peaks, districts, climate
uk-culture        → Uttarakhand folk art, dance, music, festivals, traditions
uk-general-studies → Uttarakhand polity, governance, schemes, current affairs, economy
general-gk        → national GK, Indian polity/history, science, maths, reasoning
computer          → computer awareness: hardware, software, MS Office, internet, memory, shortcuts
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

def store_rows(rows: list[dict], replace_source: str | None = None):
    """Insert rows; when replace_source is given, delete that file's old rows in
    the SAME transaction as the first batch, so a crash can't leave the paper
    half-present."""
    conn = _db()
    inserted = 0
    with conn.cursor() as cur:
        if replace_source:
            cur.execute("DELETE FROM pyq_chunks WHERE source_file = %s", (replace_source,))
            print(f"    replacing {cur.rowcount} old rows for '{replace_source}'")
        for i in range(0, len(rows), DB_BATCH):
            batch = rows[i: i + DB_BATCH]
            cur.executemany(
                """INSERT INTO pyq_chunks (subject, source_file, chunk_text, embedding, answer, format)
                   VALUES (%s, %s, %s, %s::vector, %s, %s)""",
                [
                    (
                        r["subject"],
                        r["source_file"],
                        r["chunk_text"],
                        "[" + ",".join(str(x) for x in r["embedding"]) + "]",
                        r.get("answer"),
                        r.get("format"),
                    )
                    for r in batch
                ],
            )
            conn.commit()
            inserted += len(batch)
            print(f"    stored {inserted}/{len(rows)}", flush=True)
    conn.close()


# ── per-file ingestion ─────────────────────────────────────────────────────────

def ingest_file(src_path: Path, dry_run: bool = False, replace: bool = False):
    source_file = src_path.name

    print(f"\n{'='*60}")
    print(f"File     : {source_file}")
    print(f"Exam type: {src_path.parent.name}")
    print(f"{'='*60}")

    if not dry_run and not replace and _already_ingested(source_file):
        print("  Already in DB — skipping (use --replace to re-ingest).")
        return

    # .md files ARE the digitized source — read directly, no Sarvam cost.
    if src_path.suffix.lower() == ".md":
        md_text = src_path.read_text(encoding="utf-8", errors="replace")
    else:
        md_text = digitize_pdf(src_path)

    questions = parse_questions(md_text)
    n_ans = sum(1 for q in questions if q.get("answer"))
    fmt_dist = Counter(q["format"] for q in questions)
    print(f"  Parsed {len(questions)} Hindi questions "
          f"| answers captured: {n_ans}/{len(questions)} "
          f"| formats: {dict(fmt_dist)}")

    if not questions:
        print("  No questions found — check PDF/Markdown quality.")
        return

    if dry_run:
        print("  DRY RUN — skipping classify + embed + store. Samples:")
        # show one sample of each non-plain format so shredding is visible at a glance
        shown: set[str] = set()
        for q in questions:
            if q["format"] not in shown and q["format"] != "plain":
                shown.add(q["format"])
                head = " | ".join(q["text"].splitlines())[:220]
                print(f"    [{q['format']:9}] Q{q['n']} ans={q.get('answer')}: {head}...")
        return

    subjects = classify_subjects(questions)
    dist = Counter(subjects)
    print(f"  Subject distribution: {dict(dist)}")

    print(f"  Embedding {len(questions)} questions...")
    embeddings = embed_texts([q["text"] for q in questions])

    rows = [
        {
            "subject":     subjects[i],
            "source_file": source_file,
            "chunk_text":  questions[i]["text"],
            "embedding":   embeddings[i],
            "answer":      questions[i].get("answer"),
            "format":      questions[i].get("format"),
        }
        for i in range(len(questions))
    ]

    store_rows(rows, replace_source=source_file if replace else None)
    print(f"  DONE: {len(rows)} chunks stored for '{source_file}'")


# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest PYQ papers into pyq_chunks (.md read directly; .pdf via Sarvam Vision)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--exam", metavar="EXAM_TYPE",
        help="Exam folder to ingest: vdo-vpdo | lekhpal-patwari | group-c",
    )
    group.add_argument("--all", action="store_true", help="Ingest all exam folders")
    group.add_argument(
        "--file", metavar="REL_PATH",
        help="One file, relative to corpus/pyq/ (e.g. vdo-vpdo/vdo-vpdo-2023-07-09.md)",
    )
    parser.add_argument(
        "--md-only", action="store_true",
        help="Only .md sources (skip PDFs -> no Sarvam spend)",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="Re-ingest files already in the DB (delete+insert per source_file)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse only — no classify, no embeddings, no DB writes",
    )
    args = parser.parse_args()

    if args.file:
        files = [PYQ_DIR / args.file]
        if not files[0].exists():
            print(f"ERROR: file not found: {files[0]}")
            sys.exit(1)
    else:
        if args.all:
            exam_dirs = sorted(d for d in PYQ_DIR.iterdir() if d.is_dir())
        else:
            exam_dirs = [PYQ_DIR / args.exam]
        files = []
        for exam_dir in exam_dirs:
            if not exam_dir.exists():
                print(f"ERROR: folder not found: {exam_dir}")
                sys.exit(1)
            pats = ["*.md"] if args.md_only else ["*.md", "*.pdf"]
            for pat in pats:
                files.extend(f for f in sorted(exam_dir.glob(pat))
                             if not f.name.startswith("."))

    for f in files:
        ingest_file(f, dry_run=args.dry_run, replace=args.replace)

    print("\nAll done.")
