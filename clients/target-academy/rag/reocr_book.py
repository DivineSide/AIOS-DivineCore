# -*- coding: utf-8 -*-
"""
reocr_book — re-OCR a scanned book through Sarvam doc-digitization, resumably.

WHY: the 3 uk-history books were OCR'd with Tesseract, which misreads printed
'1' as '4'/'7' — reign years and dates are corrupted (BAHI302: 239 chunks).
Sarvam Vision reads them perfectly (verified on a 10-page sample 2026-07-12:
zero impossible years, zero matra garble). Cost: ₹0.5/page.

RESUMABLE: the book is split into 10-page jobs (Sarvam's cap). Each completed
job's markdown is checkpointed to .reocr/<book>/<NNN>-<NNN>.md and skipped on
rerun — so when a Sarvam account's credit runs out mid-book, swap
SARVAM_API_KEY in .env and rerun the same command; it resumes where it died.

When all pieces exist, they concatenate to .reocr/<book>.full.md — the input
for re-ingesting the book (delete its book_chunks rows, run ingest with the
sidecar; ingest integration is a separate step).

Usage:
    python reocr_book.py --book "uk-history/BAHI302.pdf"
    python reocr_book.py --book "uk-history/BAHI302.pdf" --status   # progress only
"""

import argparse
import io
import os
import re
import sys
import zipfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)

import pymupdf as fitz
from dotenv import load_dotenv

BASE      = Path(__file__).resolve().parents[1]
BOOKS_DIR = BASE / "corpus" / "book-sources"
REOCR_DIR = Path(__file__).resolve().parent / ".reocr"   # gitignored with .checkpoints
PAGES_PER_JOB = 10   # Sarvam doc-digitization hard cap


def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return


_load_env()


def _sarvam():
    from sarvamai import SarvamAI
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        raise RuntimeError("SARVAM_API_KEY not set in .env")
    return SarvamAI(api_subscription_key=key)


def _digitize_pdf_file(pdf_path: Path) -> str:
    """One <=10-page PDF -> markdown via a Sarvam doc-digitization job."""
    client = _sarvam()
    job = client.document_intelligence.create_job(language="hi-IN", output_format="md")
    job.upload_file(str(pdf_path))
    job.start()
    status = job.wait_until_complete(poll_interval=4.0, timeout=420)
    if status.job_state != "Completed":
        raise RuntimeError(f"Sarvam job {job.job_id}: {status.job_state}: {status.error_message}")
    tmp_zip = pdf_path.with_suffix(".zip")
    try:
        job.download_output(str(tmp_zip))
        with zipfile.ZipFile(tmp_zip) as zf:
            md = [n for n in zf.namelist() if n.endswith(".md")]
            if not md:
                raise RuntimeError(f"no .md in Sarvam output for {pdf_path.name}")
            return zf.read(md[0]).decode("utf-8")
    finally:
        tmp_zip.unlink(missing_ok=True)


def reocr(book_rel: str, status_only: bool = False):
    src = BOOKS_DIR / book_rel
    if not src.exists():
        print(f"ERROR: not found: {src}")
        sys.exit(1)

    doc = fitz.open(str(src))
    total = doc.page_count
    out_dir = REOCR_DIR / src.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    ranges = [(s, min(s + PAGES_PER_JOB - 1, total - 1))
              for s in range(0, total, PAGES_PER_JOB)]
    done = {p.name for p in out_dir.glob("*.md") if re.match(r"\d{3}-\d{3}\.md$", p.name)}

    print(f"{src.name}: {total} pages, {len(ranges)} jobs, "
          f"{len(done)} already checkpointed, ~₹{(total - len(done)*PAGES_PER_JOB)*0.5:.0f} remaining")
    if status_only:
        return

    for s, e in ranges:
        name = f"{s:03d}-{e:03d}.md"
        if name in done:
            continue
        piece = out_dir / f"_tmp_{s:03d}.pdf"
        part = fitz.open()
        part.insert_pdf(doc, from_page=s, to_page=e)
        part.save(str(piece))
        part.close()
        try:
            md = _digitize_pdf_file(piece)
        except Exception as exc:
            print(f"  pages {s}-{e}: FAILED ({exc})")
            print("  Stopping. If this is credit exhaustion: swap SARVAM_API_KEY "
                  "in .env and rerun the same command — completed pieces are kept.")
            sys.exit(2)
        finally:
            piece.unlink(missing_ok=True)
        (out_dir / name).write_text(md, encoding="utf-8")
        print(f"  pages {s}-{e}: OK ({len(md)} chars)", flush=True)

    # all pieces present -> assemble
    pieces = sorted(p for p in out_dir.glob("*.md") if re.match(r"\d{3}-\d{3}\.md$", p.name))
    full = "\n\n".join(p.read_text(encoding="utf-8") for p in pieces)
    full_path = REOCR_DIR / f"{src.stem}.full.md"
    full_path.write_text(full, encoding="utf-8")
    print(f"\nDONE: {full_path} ({len(full):,} chars from {len(pieces)} pieces)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Resumable Sarvam re-OCR of a scanned book.")
    ap.add_argument("--book", required=True,
                    help="path relative to corpus/book-sources/, e.g. uk-history/BAHI302.pdf")
    ap.add_argument("--status", action="store_true", help="show progress, run nothing")
    args = ap.parse_args()
    reocr(args.book, status_only=args.status)
