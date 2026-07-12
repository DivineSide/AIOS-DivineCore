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
import re
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
import anthropic
import pytesseract

BASE        = Path(__file__).resolve().parents[1]
BOOKS_DIR   = BASE / "corpus" / "book-sources"
CHECKPOINT  = Path(__file__).resolve().parent / ".checkpoints"

# Kruti-Dev -> Unicode converter lives in the pipeline package (already battle-
# tested + self-tested there). Some digital PDFs have a Kruti-Dev legacy text
# layer: PyMuPDF extracts real characters, but they're ASCII glyphs that render
# as Devanagari only in the Kruti Dev font — as raw text they're Latin gibberish
# ("Hkkjr" = भारत). If ingested as-is they poison the whole book. We detect and
# convert BEFORE segmentation so Haiku + embeddings only ever see real Unicode.
sys.path.insert(0, str(BASE / "pipeline"))
from krutidev import krutidev_to_unicode
CHECKPOINT.mkdir(exist_ok=True)

EMBED_MODEL      = "openai/text-embedding-3-small"  # served via OpenRouter (OpenAI direct
                                                     # key is quota-exhausted). Same 1536-dim
                                                     # model — vectors stay compatible with
                                                     # everything already in book_chunks.
SEGMENT_MODEL    = "openai/gpt-4o-mini"  # served via OpenRouter. This is the ORIGINAL
                                          # segmentation model (before the direct OpenAI
                                          # key ran out of quota) — the best-retrieving
                                          # books already in book_chunks (Laxmikant 0.58,
                                          # Hindi grammar 0.41-0.55) were segmented by this
                                          # exact model. We briefly moved to Haiku as a
                                          # stopgap; measured cost was ~19x gpt-4o-mini's
                                          # (~$0.012/call vs ~$0.0006/call) with only a
                                          # modest fidelity edge (finer-grained chunks,
                                          # both equally accurate) — not worth the price
                                          # gap given 4o-mini's proven retrieval track record.
CHUNK_CHARS      = 8000
WINDOW_OVERLAP   = 600   # each window re-includes the last 600 chars of the previous
                         # one, so a concept straddling an 8000-char boundary is seen
                         # whole by at least one window. Duplicate chunks the overlap
                         # produces are removed by _dedupe_chunks() before embedding.
BATCH_CHARS      = 80_000
BATCH_CHUNKS     = 64
DB_BATCH         = 50
SEGMENT_WORKERS  = 4   # was 8 — the concurrency itself was causing the timeouts

# ---------------------------------------------------------------------------
# env + clients
# ---------------------------------------------------------------------------
def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return

_load_env()
_embed: OpenAI | None = None
_claude: anthropic.Anthropic | None = None

def _oai() -> OpenAI:
    """Segmentation + embedding client. OpenRouter when OPENROUTER_API_KEY is
    present; otherwise the direct OpenAI key (works again as of 2026-07-12 —
    the OpenRouter key was removed from .env). Model names differ per route:
    OpenRouter prefixes "openai/"."""
    global _embed
    if _embed is None:
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if key:
            _embed = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1",
                            timeout=90, max_retries=5)
        else:
            _embed = OpenAI(timeout=90, max_retries=5)  # direct OPENAI_API_KEY
    return _embed


def _model_name(name: str) -> str:
    """Map an "openai/<model>" id to the right form for the active route."""
    if os.environ.get("OPENROUTER_API_KEY", ""):
        return name
    return name.removeprefix("openai/")

def _anthropic() -> anthropic.Anthropic:
    global _claude
    if _claude is None:
        _claude = anthropic.Anthropic(timeout=90, max_retries=5)
    return _claude

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
    """A book is "digital" only if MOST of its pages carry real text — a text
    cover/title page on an otherwise-scanned book must not trigger this, or
    the whole book silently gets 1-2 pages of "content" and is marked done.
    """
    doc = fitz.open(str(path))
    total = len(doc)
    sample_idx = range(total) if total <= 20 else [
        int(i * (total - 1) / 19) for i in range(20)
    ]
    with_text = sum(1 for i in sample_idx if len(doc[i].get_text().strip()) > 100)
    return (with_text / len(sample_idx)) >= 0.7

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
# Kruti Dev's most common Devanagari mappings, as they appear in raw extracted
# text. Chosen to be distinctive of Kruti-Dev Hindi and rare in real English:
# these are the Kruti glyphs for क, की, में, प्र, भा, ्या, half-letters, etc.
_KD_SIGNATURES = ("dk ", " dh ", " esa ", "Hkk", "izk", "iz'", "vè;", ".kk",
                  "'kk", "Lo;", "Ùk", "{k", "T;k", "|k", "/kk")

def _kd_score(s: str) -> tuple[float, float]:
    """Return (devanagari_ratio, kd_signature_density) for a text sample."""
    if not s.strip():
        return 1.0, 0.0   # empty -> treat as "definitely not KD"
    dev = len(_DEVANAGARI_RE.findall(s))
    letters = sum(1 for c in s if c.isalpha())
    dev_ratio = dev / letters if letters else 1.0
    hits = sum(s.count(sig) for sig in _KD_SIGNATURES)
    density = hits / len(s)
    return dev_ratio, density

def is_krutidev(text: str) -> bool:
    """Kruti-Dev text has near-zero real Devanagari AND a high density of KD
    signature digraphs. We sample the MIDDLE of the book (front matter is often
    English copyright/preface pages that can false-positive), and require BOTH
    conditions so an English-heavy book never trips it.
    """
    n = len(text)
    if n < 2000:
        samples = [text]
    else:
        # three windows: 25%, 50%, 75% through the book
        samples = [text[int(n * f): int(n * f) + 15000] for f in (0.25, 0.5, 0.75)]
    kd_votes = 0
    for s in samples:
        dev_ratio, density = _kd_score(s)
        # KD Hindi: <15% real Devanagari AND >1 signature per ~120 chars.
        if dev_ratio < 0.15 and density > (1 / 120):
            kd_votes += 1
    # majority of sampled regions must look like KD
    return kd_votes >= (len(samples) + 1) // 2

def _maybe_krutidev(text: str) -> str:
    if is_krutidev(text):
        print("  Kruti Dev text layer detected — converting to Unicode Devanagari...")
        converted = krutidev_to_unicode(text)
        dev_after = len(_DEVANAGARI_RE.findall(converted[:20000]))
        print(f"    conversion done ({dev_after} Devanagari chars in first 20k after convert).")
        return converted
    return text

# Sarvam re-OCR sidecars (written by reocr_book.py). When one exists for a book,
# it is ALWAYS preferred over local extraction — Sarvam Vision reads Hindi print
# correctly where Tesseract mangles digits ('1'->'4'/'7') and conjuncts.
REOCR_DIR = Path(__file__).resolve().parent / ".reocr"


def _strip_sarvam_html(text: str) -> str:
    """Sarvam markdown embeds tables as raw HTML. Flatten: cells of a row join
    with ' | ', tags become line breaks. Keeps TOC/reference tables readable as
    text (downstream junk rules drop them where they deserve it)."""
    text = re.sub(r"</td>\s*<td[^>]*>", " | ", text)
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"<[^>]+>", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def extract_text(path: Path) -> str:
    sidecar = REOCR_DIR / f"{path.stem}.full.md"
    if sidecar.exists():
        print(f"  Sarvam re-OCR sidecar found ({sidecar.name}) — using it, no local OCR.")
        return _strip_sarvam_html(sidecar.read_text(encoding="utf-8"))
    if has_text_layer(path):
        print("  Digital PDF detected — extracting text layer...")
        text = extract_text_digital(path)
        # Guard against a digital PDF whose text layer is much thinner than
        # its page count implies (e.g. mixed scanned/digital pages) — better
        # to OCR everything than silently ingest a fragment as "the book".
        pages = fitz.open(str(path)).page_count
        if len(text) < pages * 200:
            print(f"  Text layer too thin ({len(text)} chars / {pages} pages) — falling back to OCR...")
            return _maybe_krutidev(extract_text_scanned(path))
        return _maybe_krutidev(text)
    else:
        print("  Scanned PDF detected — running Tesseract OCR...")
        return extract_text_scanned(path)

# ---------------------------------------------------------------------------
# topic-aware segmentation (OFFSET method)
# ---------------------------------------------------------------------------
# We split the window into sentences IN CODE, number them, and ask the model
# only WHERE each topic-coherent chunk STARTS (a sentence number) + a topic
# label. We then slice OUR sentence list at those boundaries. The model never
# echoes body text, so output tokens collapse from ~4900 to ~300 (Haiku output
# is billed 5x input — echoing the whole book back cost ~$20/book; this ~$3-7).
#
# Bonus quality win: because chunk text is sliced from the ORIGINAL extraction,
# it is byte-for-byte exact — the model can't silently paraphrase or "fix"
# Devanagari while copying (which the echo method risked, especially in Hindi).

# Devanagari danda ।, double danda ॥, ASCII . ! ? and PARAGRAPH breaks (2+
# newlines) end a sentence. A single newline does NOT: OCR/PDF extraction emits
# one per PRINTED LINE, and splitting there made every ~60-char print line a
# "sentence" — the model's "1-6 sentence" chunks became one-fact fragments
# (median 94-500 chars in book_chunks) and page headers became standalone
# chunks. Root cause of the fragmentation that book_passages had to repair.
_SENT_SPLIT = re.compile(r"(?<=[।॥.!?])\s+|\n{2,}")

def _split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_SPLIT.split(text)]
    return [s for s in parts if s]

SEGMENT_PROMPT = """You are a Hindi/English text segmenter for an educational RAG system.
You are given a document window already split into numbered sentences.
Group CONSECUTIVE sentences into topic-coherent chunks. Each chunk covers ONE topic.

Return ONLY a JSON object of this exact shape, no prose, no markdown fences:
{"chunks": [{"topic": "<3-8 word topic>", "start": <sentence number this chunk starts at>}]}

Rules:
- "start" is the 1-based number of the FIRST sentence in that chunk.
- Chunks must be in order; the first chunk starts at 1; each next start is greater.
- Do NOT return sentence text — only the starting sentence number + a topic.
- Aim for chunks of roughly 1-6 sentences, each a single coherent concept."""

def _segment_window(window: str) -> list[dict]:
    sentences = _split_sentences(window)
    if not sentences:
        return []
    numbered = "\n".join(f"[{i+1}] {s}" for i, s in enumerate(sentences))

    resp = _oai().chat.completions.create(
        model=_model_name(SEGMENT_MODEL),
        max_tokens=2048,          # boundaries only — never the body text
        messages=[
            {"role": "system", "content": SEGMENT_PROMPT},
            {"role": "user", "content": numbered},
        ],
        response_format={"type": "json_object"},
    )
    raw = (resp.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    boundaries = data.get("chunks", [])

    # Keep only valid, in-range start indices; slice OUR sentences at them.
    # De-dupe by start (keep first topic seen for a repeated start) so a model
    # slip (two chunks claiming the same sentence) can't produce a zero-length
    # or out-of-order slice.
    n = len(sentences)
    seen_starts = set()
    valid = []
    for b in boundaries:
        try:
            start = int(b.get("start", 0))
        except (TypeError, ValueError):
            continue
        if 1 <= start <= n and start not in seen_starts:
            seen_starts.add(start)
            valid.append((start, str(b.get("topic", "")).strip()))
    valid.sort(key=lambda x: x[0])
    # Guarantee sentence 1 is covered (no leading text is ever dropped).
    if not valid or valid[0][0] != 1:
        valid = [(1, valid[0][1] if valid else "")] + [v for v in valid if v[0] > 1]

    chunks = []
    for idx, (start, topic) in enumerate(valid):
        end = valid[idx + 1][0] - 1 if idx + 1 < len(valid) else n
        body = " ".join(sentences[start - 1:end])   # exact source text
        if body.strip():
            chunks.append({"topic": topic, "text": body})
    return chunks

def _run_windows(windows: list[str]) -> list[list[dict] | None]:
    """One pass over all windows. None = failed (caller decides retry vs drop)."""
    total = len(windows)
    results: list[list[dict] | None] = [None] * total
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=SEGMENT_WORKERS) as ex:
        future_to_idx = {ex.submit(_segment_window, w): i for i, w in enumerate(windows)}
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                print(f"    window {idx} failed: {e}")
                results[idx] = None
            completed += 1
            print(f"    window {completed}/{total} done", flush=True)
    return results

def _normalize(s: str) -> str:
    """Collapse whitespace + lowercase for dedup comparison only (stored text is untouched)."""
    return " ".join(s.split()).lower()


def _dedupe_chunks(chunks: list[dict]) -> list[dict]:
    """Overlapping windows re-segment the same boundary text, so the same passage
    can come back as a chunk twice. Drop later duplicates by normalized text.
    Also drops a chunk fully contained inside an already-kept longer chunk.
    """
    kept: list[dict] = []
    seen_norms: list[str] = []
    for c in chunks:
        norm = _normalize(c.get("text", ""))
        if not norm:
            continue
        if any(norm == k or norm in k for k in seen_norms):
            continue
        kept.append(c)
        seen_norms.append(norm)
    return kept


def segment_text(text: str) -> list[dict]:
    windows = []
    # Step by CHUNK_CHARS - WINDOW_OVERLAP so consecutive windows share their
    # boundary region — a topic spanning an 8000-char cut is seen whole by one
    # of them. The duplicate chunks this creates are removed after segmentation.
    step = max(1, CHUNK_CHARS - WINDOW_OVERLAP)
    for i in range(0, len(text), step):
        w = text[i: i + CHUNK_CHARS]
        if w.strip():
            windows.append(w)
        if i + CHUNK_CHARS >= len(text):
            break

    total = len(windows)
    print(f"  Segmenting {total} windows ({SEGMENT_WORKERS} concurrent)...")
    results = _run_windows(windows)

    # Retry failed windows once, sequentially — most failures here are
    # timeouts from concurrent load, which a lone retry usually clears.
    failed_idx = [i for i, r in enumerate(results) if r is None]
    if failed_idx:
        print(f"  Retrying {len(failed_idx)} failed window(s) sequentially...")
        for idx in failed_idx:
            try:
                results[idx] = _segment_window(windows[idx])
                print(f"    window {idx} recovered on retry")
            except Exception as e:
                print(f"    window {idx} failed again: {e}")
                results[idx] = None

    still_failed = [i for i, r in enumerate(results) if r is None]
    if still_failed:
        lost_chars = sum(len(windows[i]) for i in still_failed)
        print(f"  WARNING: {len(still_failed)}/{total} window(s) permanently failed "
              f"— ~{lost_chars:,} chars of book content NOT ingested "
              f"(windows: {still_failed})")

    chunks = []
    for r in results:
        if r:
            chunks.extend(r)

    before = len(chunks)
    chunks = _dedupe_chunks(chunks)
    if before != len(chunks):
        print(f"  Deduped {before - len(chunks)} overlap-duplicate chunk(s) "
              f"({before} -> {len(chunks)}).")
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
        resp = _oai().embeddings.create(model=_model_name(EMBED_MODEL), input=texts)
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
    rows = []
    for c in chunks:
        vec = "[" + ",".join(str(x) for x in c["embedding"]) + "]"
        rows.append((book_name, subject, c.get("topic", ""), c.get("text", ""), vec))

    # A single connection held open across thousands of inserts (potentially
    # minutes) can be dropped by Supabase's pooler mid-stream — observed
    # "server closed the connection unexpectedly" partway through large books.
    # Reconnect per batch, with one retry-with-fresh-connection on failure, so
    # a transient drop costs one batch's retry, not the whole book's progress.
    conn = _db()
    inserted = 0
    for i in range(0, len(rows), DB_BATCH):
        batch = rows[i: i + DB_BATCH]
        for attempt in range(2):
            try:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO book_chunks (book_name, subject, topic, chunk_text, embedding) VALUES (%s,%s,%s,%s,%s::vector)",
                        batch,
                    )
                conn.commit()
                break
            except psycopg2.OperationalError as e:
                print(f"    batch at {inserted} failed ({e}) — reconnecting and retrying...", flush=True)
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _db()
                if attempt == 1:
                    raise
        inserted += len(batch)
        print(f"    inserted {inserted}/{len(rows)}", flush=True)
    conn.close()

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def ingest(book_arg: str, replace: bool = False):
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

    checkpoint = CHECKPOINT / f"{book_name}.chunks.json"

    if replace:
        # Re-ingest (e.g. after a Sarvam re-OCR): the old DB rows AND the old
        # checkpoint both hold the damaged extraction — the checkpoint would
        # silently resurrect it, so it must go too.
        if checkpoint.exists():
            checkpoint.unlink()
            print("  --replace: stale checkpoint deleted (held the old extraction).")
        conn = _db()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM book_chunks WHERE book_name = %s", (book_name,))
            print(f"  --replace: {cur.rowcount} old rows deleted from book_chunks.")
        conn.commit()
        conn.close()
    elif _already_ingested(book_name):
        print(f"  Already in DB — skipping (use --replace to re-ingest).")
        return

    chunks = None
    if checkpoint.exists():
        print(f"  Checkpoint found — loading segments from disk...")
        with open(checkpoint, encoding="utf-8") as f:
            chunks = json.load(f)
        if chunks:
            print(f"  Loaded {len(chunks)} chunks from checkpoint.")
        else:
            # A failed earlier run can leave an empty "[]" checkpoint behind;
            # trusting it would silently ingest 0 rows. Re-extract instead.
            print("  Checkpoint is EMPTY (stale from a failed run) — ignoring it.")
            chunks = None

    if chunks is None:
        text = extract_text(book_path)
        if not text.strip():
            print("  ERROR: no text extracted.")
            return
        print(f"  Extracted {len(text):,} chars.")

        chunks = segment_text(text)
        print(f"  Segmented into {len(chunks)} chunks.")

        if not chunks:
            print("  ERROR: segmentation produced 0 chunks — not saving checkpoint.")
            return

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
    parser.add_argument("--replace", action="store_true",
                        help="Delete the book's DB rows + stale checkpoint and re-ingest "
                             "(use after a Sarvam re-OCR)")
    args = parser.parse_args()
    ingest(args.book, replace=args.replace)
