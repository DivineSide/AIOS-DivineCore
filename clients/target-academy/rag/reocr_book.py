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


def _keys() -> list[str]:
    """Key pool: SARVAM_API_KEY plus SARVAM_API_KEY_2, _3, ... — fresh free
    accounts are ₹100 each, so a big book spans several. Rotation is automatic
    on credit exhaustion; order = env-var order."""
    keys = []
    base = os.environ.get("SARVAM_API_KEY", "")
    if base:
        keys.append(base)
    n = 2
    while (k := os.environ.get(f"SARVAM_API_KEY_{n}", "")):
        keys.append(k)
        n += 1
    if not keys:
        raise RuntimeError("No SARVAM_API_KEY[_N] set in .env")
    return keys


_key_idx = 0


def _sarvam():
    from sarvamai import SarvamAI
    return SarvamAI(api_subscription_key=_keys()[_key_idx])


def _is_credit_error(exc: Exception) -> bool:
    # Sarvam signals credit exhaustion in (at least) two shapes:
    #   400 "Insufficient credits for N pages"  (mid-account)
    #   429 "No credits available." / insufficient_quota_error  (fully dry)
    s = str(exc).lower()
    return ("insufficient credits" in s or "no credits available" in s
            or "insufficient_quota" in s)


def _is_transient_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(m in s for m in ("disconnected", "timeout", "timed out", "connection",
                                "502", "503", "429", "internal server"))


def _digitize_pdf_file(pdf_path: Path) -> str:
    """One <=10-page PDF -> markdown via a Sarvam doc-digitization job.
    Rotates to the next key in the pool when the current account runs dry;
    retries transient server errors (disconnects/timeouts) with backoff."""
    global _key_idx
    import time
    transient_left = 3
    while True:
        try:
            client = _sarvam()
            job = client.document_intelligence.create_job(language="hi-IN", output_format="md")
            job.upload_file(str(pdf_path))
            job.start()
            status = job.wait_until_complete(poll_interval=4.0, timeout=420)
            if status.job_state != "Completed":
                raise RuntimeError(f"Sarvam job {job.job_id}: {status.job_state}: {status.error_message}")
            break
        except Exception as exc:
            if _is_credit_error(exc) and _key_idx + 1 < len(_keys()):
                _key_idx += 1
                print(f"  [key pool] credit exhausted — rotating to key #{_key_idx + 1}", flush=True)
                continue
            if _is_transient_error(exc) and transient_left > 0:
                transient_left -= 1
                wait = 15 * (3 - transient_left)
                print(f"  [transient] {exc} — retrying in {wait}s "
                      f"({transient_left} retries left)", flush=True)
                time.sleep(wait)
                continue
            raise
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
    # .strip() the stem: MuPDF's C path handling silently drops a trailing
    # space that Python's own pathlib/Windows APIs preserve (mkdir + .exists()
    # succeed against the space-suffixed path, but part.save() then fails with
    # "No such file or directory" because MuPDF looks for the stripped name) —
    # hit on "Kiran SSC GK Hindi .pdf" (stem ends in a space) 2026-07-19.
    out_dir = REOCR_DIR / src.stem.strip()
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

    # all pieces present -> assemble. Sarvam inlines photo plates as base64
    # images (single 500KB "![Image](data:...)" lines) — pure bloat for a text
    # corpus, stripped here so full.md holds only text.
    pieces = sorted(p for p in out_dir.glob("*.md") if re.match(r"\d{3}-\d{3}\.md$", p.name))
    parts = []
    for p in pieces:
        t = p.read_text(encoding="utf-8")
        t = re.sub(r"!\[[^\]]*\]\(data:[^)]*\)", "", t)
        parts.append(t)
    full = "\n\n".join(parts)
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
