# -*- coding: utf-8 -*-
"""
translate_book — one-time offline English -> Hindi translation of a book's
extracted text, for an English-source book we still want in the Hindi corpus.

WHY offline, not a live pipeline stage: injecting English passages straight
into generation would (a) risk English phrasing/register bleeding into the
Hindi question stem, and (b) silently break the lexical/BM25 half of hybrid
retrieval, since queries are Hindi tokens and an English passage never matches
on that channel. Translating once, up front, keeps book_passages Hindi-only
like every other source -- no new failure mode in the live path.

Reads:  a UTF-8 .txt of extracted English text (chunk of a book, e.g. one unit)
Writes: a Hindi .md sidecar, resumably (per-chunk checkpoints so a network
        drop mid-run resumes instead of restarting + re-paying).

RESUMABLE: each translated chunk is checkpointed to
.translate/<stem>/<NNNN>.md and skipped on rerun. When all chunks exist they
concatenate to the output .md.

The output is NOT auto-ingested -- review it against the English source, then
place it at .reocr/<book-stem>.full.md (ingest.py's sidecar path) manually, so
a bad translation never silently enters the corpus.

Usage:
    python translate_book.py --in geo_unit_raw.txt --out uttarakhand-geography-himanshu.hi.md
"""

import argparse
import io
import os
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
CKPT_DIR = Path(__file__).resolve().parent / ".translate"   # gitignored like .reocr

CHUNK_CHARS = 5000  # keep each call well under the model's output budget
MODEL = os.environ.get("TRANSLATE_MODEL", "gpt-5.4-nano")

for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
    if candidate.exists():
        load_dotenv(candidate)
        break

_SYSTEM = (
    "You translate Indian competitive-exam study material about Uttarakhand "
    "from English to Hindi (Devanagari). RULES: "
    "1. Preserve EVERY fact, number, date, percentage, elevation and place "
    "name exactly -- do not summarize, drop, round, or add anything. "
    "2. Keep proper nouns (people, places, rivers, ranges, schemes) accurate; "
    "render well-known names in standard Hindi spelling, keep English "
    "acronyms (FSI, NRHM) as-is. "
    "3. Preserve markdown tables and heading structure. "
    "4. Use the vocabulary a UKSSSC Hindi paper uses (e.g. दर्रा for pass, "
    "हिमनद for glacier, अपवाह for drainage, वनावरण for forest cover). "
    "5. Output ONLY the Hindi translation -- no commentary, no English "
    "preamble, no 'Here is the translation'."
)


def _client():
    from openai import OpenAI
    return OpenAI(timeout=90, max_retries=3)


def _chunk(text: str, size: int) -> list[str]:
    # split on blank lines so a chunk boundary never lands mid-sentence
    paras = text.split("\n")
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 1 > size:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def translate(in_path: Path, out_path: Path):
    if not in_path.exists():
        print(f"ERROR: not found: {in_path}")
        sys.exit(1)

    text = in_path.read_text(encoding="utf-8")
    chunks = _chunk(text, CHUNK_CHARS)
    ckpt = CKPT_DIR / in_path.stem
    ckpt.mkdir(parents=True, exist_ok=True)
    done = {p.name for p in ckpt.glob("*.md")}
    print(f"{in_path.name}: {len(text):,} chars -> {len(chunks)} chunks "
          f"({len(done)} already checkpointed)")

    client = _client()
    for i, chunk in enumerate(chunks):
        name = f"{i:04d}.md"
        if name in done:
            continue
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": chunk},
                ],
            )
        except Exception as exc:
            print(f"  chunk {i+1}/{len(chunks)}: FAILED ({exc})")
            print("  Stopping. Rerun the same command — completed chunks are kept.")
            sys.exit(2)
        translated = (resp.choices[0].message.content or "").strip()
        if not translated:
            print(f"  chunk {i+1}/{len(chunks)}: EMPTY output — keeping English original for this chunk")
            translated = chunk
        (ckpt / name).write_text(translated, encoding="utf-8")
        print(f"  chunk {i+1}/{len(chunks)}: OK ({len(translated)} chars)", flush=True)
        time.sleep(0.2)

    pieces = sorted(ckpt.glob("*.md"), key=lambda p: p.name)
    full = "\n\n".join(p.read_text(encoding="utf-8") for p in pieces)
    out_path.write_text(full, encoding="utf-8")
    print(f"\nDONE: {out_path} ({len(full):,} chars from {len(pieces)} chunks)")
    print("Review against the English source before promoting to "
          ".reocr/<book-stem>.full.md and running ingest.py.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="One-time resumable English->Hindi translation of extracted book text.")
    ap.add_argument("--in", dest="in_path", required=True, help="UTF-8 .txt of extracted English text")
    ap.add_argument("--out", dest="out_path", required=True, help="output Hindi .md path")
    args = ap.parse_args()
    translate(Path(args.in_path), Path(args.out_path))
