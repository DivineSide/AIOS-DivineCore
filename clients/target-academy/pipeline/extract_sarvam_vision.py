# -*- coding: utf-8 -*-
"""Sarvam Vision (Document Digitisation) OCR path.

Why this exists: legacy Target Academy papers store Hindi as Kruti-Dev — a
font-encoding where Devanagari is written with Latin glyph codes. The .docx
TEXT layer therefore hands us ambiguous bytes ("LFkku" could be Kruti-Dev for
"स्थान" OR a real English token), and no deterministic converter can tell the
two apart, so mixed Hindi/English papers come out part-gibberish.

Sarvam Vision sidesteps this entirely: it reads the document as an IMAGE and
returns clean Unicode (it's an Indian-language OCR model). We feed that clean
text into the same question-structuring step the .docx path already uses.

Flow (raw REST, job-based async — no SDK dependency, httpx is already present):
  1. POST  /doc-digitization/job/v1                      -> job_id
  2. POST  /doc-digitization/job/v1/upload-files         -> presigned upload URL
  3. PUT   <presigned url>  (the PDF bytes)
  4. POST  /doc-digitization/job/v1/{job_id}/start
  5. GET   /doc-digitization/job/v1/{job_id}/status      -> poll until Completed
  6. POST  /doc-digitization/job/v1/{job_id}/download-files -> presigned output URL(s)
  7. GET   <presigned url>  (the markdown/JSON output)

Constraints (from the API docs): 10 pages per job (we batch), 200 MB, 10 req/min.
Input must be PDF/PNG/JPEG (NO docx) — we convert .docx -> PDF first via the
LibreOffice helper the answer-key builder already uses.

This module only produces CLEAN TEXT. extract_docx.extract_from_text() then turns
that text into the universal questions JSON, so all the salvage/dedup logic is
shared.
"""
import io
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))

BASE_URL = "https://api.sarvam.ai/doc-digitization/job/v1"
PAGES_PER_JOB = 10          # API hard limit
POLL_INTERVAL_S = 3
POLL_TIMEOUT_S = 300        # 5 min per batch; OCR of <=10 pages is fast
_TERMINAL_OK = {"Completed", "PartiallyCompleted"}
_TERMINAL_BAD = {"Failed"}


def _keys() -> list[str]:
    """All configured Sarvam keys, in priority order, deduped. We keep a POOL so
    that when one key is exhausted (out of credits / rate-limited / revoked) we
    rotate to the next before giving up on Sarvam entirely.

    Sources (highest priority first):
      SARVAM_VISION_KEYS / SARVAM_API_KEYS — comma-separated pools
      SARVAM_VISION_KEY  / SARVAM_API_KEY  — single-key back-compat
    """
    raw = []
    for var in ("SARVAM_VISION_KEYS", "SARVAM_API_KEYS",
                "SARVAM_VISION_KEY", "SARVAM_API_KEY"):
        val = os.environ.get(var, "")
        if val:
            raw.extend(val.split(","))
    keys, seen = [], set()
    for k in raw:
        k = k.strip()
        if k and k not in seen:
            seen.add(k)
            keys.append(k)
    if not keys:
        raise RuntimeError("No Sarvam key set (SARVAM_VISION_KEY[S] / "
                           "SARVAM_API_KEY[S]) — required for Sarvam Vision.")
    return keys


def _headers(key: str) -> dict:
    return {"api-subscription-key": key}


# Errors that mean "this KEY is unusable — try the next one" (credits/auth/rate),
# as opposed to a document/content error (retrying with another key won't help).
_KEY_DEAD_SIGNALS = ("insufficient credit", "insufficient_credit", "credit",
                     "quota", "rate limit", "rate_limit", "ratelimit",
                     "unauthorized", "forbidden", "invalid api", "subscription",
                     "authentication", "permission", "402", "401", "403", "429")


def _is_key_dead(exc: Exception) -> bool:
    """True when the failure is about the KEY (rotate), not the document."""
    msg = str(exc).lower()
    return any(sig in msg for sig in _KEY_DEAD_SIGNALS)


def _client() -> httpx.Client:
    return httpx.Client(timeout=60.0)


def _docx_to_pdf(src: Path) -> Path:
    """Sarvam takes PDF/PNG/JPEG, not .docx — render the doc to PDF with the same
    LibreOffice path the answer-key builder uses."""
    import subprocess
    out_dir = src.parent
    subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir",
         str(out_dir), str(src)],
        check=True, capture_output=True, timeout=180,
    )
    pdf = src.with_suffix(".pdf")
    if not pdf.exists():
        raise RuntimeError(f"docx->pdf conversion produced no file for {src.name}")
    return pdf


def _split_pdf(pdf: Path) -> list[Path]:
    """Split a PDF into <=PAGES_PER_JOB chunks so each OCR job is within the
    10-page API cap. Returns the chunk paths (the original if it already fits)."""
    import fitz
    doc = fitz.open(str(pdf))
    n = doc.page_count
    if n <= PAGES_PER_JOB:
        doc.close()
        return [pdf]
    chunks = []
    for start in range(0, n, PAGES_PER_JOB):
        end = min(start + PAGES_PER_JOB, n)
        part = fitz.open()
        part.insert_pdf(doc, from_page=start, to_page=end - 1)
        out = pdf.with_name(f"{pdf.stem}_p{start + 1}-{end}.pdf")
        part.save(str(out))
        part.close()
        chunks.append(out)
    doc.close()
    return chunks


def _digitize_one(pdf: Path, client: httpx.Client, language: str, key: str) -> str:
    """Run one <=10-page PDF through the Sarvam Vision job flow -> markdown text.
    All requests use the SAME `key` (the pool rotates at the digitize_to_text
    level, so a whole document is OCR'd on one key)."""
    # 1. create job
    r = client.post(BASE_URL, headers=_headers(key),
                    json={"job_parameters": {"language": language, "output_format": "md"}})
    r.raise_for_status()
    job_id = r.json()["job_id"]

    # 2. get the presigned upload URL for our file
    r = client.post(f"{BASE_URL}/upload-files", headers=_headers(key),
                    json={"job_id": job_id, "files": [pdf.name]})
    r.raise_for_status()
    upload_urls = r.json().get("upload_urls", {})
    target = upload_urls.get(pdf.name)
    file_url = target.get("file_url") if isinstance(target, dict) else target
    if not file_url:
        raise RuntimeError(f"Sarvam returned no upload URL for {pdf.name}")

    # 3. PUT the bytes to the presigned (Azure) URL. Azure block blobs need this header.
    data = pdf.read_bytes()
    put = client.put(file_url, content=data,
                     headers={"x-ms-blob-type": "BlockBlob"})
    put.raise_for_status()

    # 4. start. Surface the response BODY on failure — a bare raise_for_status()
    # hides Sarvam's actual reason (e.g. an invalid job param or unsupported
    # output_format), which is exactly what we need to diagnose a 400.
    st = client.post(f"{BASE_URL}/{job_id}/start", headers=_headers(key))
    if st.status_code >= 400:
        body = ""
        try:
            body = st.text[:500]
        except Exception:
            pass
        raise RuntimeError(
            f"Sarvam /start failed ({st.status_code}) for job {job_id}: {body}")

    # 5. poll status — measure by WALL-CLOCK, not iteration count. Each loop does
    #    a network GET + a sleep, so counting iterations under-counts real elapsed
    #    time and can false-timeout a slow-but-valid OCR job (which then falls back
    #    to the inferior garbled text layer). time.monotonic() is immune to that.
    start_t = time.monotonic()
    state = "Accepted"
    while time.monotonic() - start_t < POLL_TIMEOUT_S:
        s = client.get(f"{BASE_URL}/{job_id}/status", headers=_headers(key))
        s.raise_for_status()
        state = s.json().get("job_state", "")
        if state in _TERMINAL_OK or state in _TERMINAL_BAD:
            break
        time.sleep(POLL_INTERVAL_S)
    if state in _TERMINAL_BAD or state not in _TERMINAL_OK:
        raise RuntimeError(f"Sarvam Vision job {job_id} ended in state {state!r}")
    # PartiallyCompleted = OCR skipped some pages. We still USE what came back
    # (it's clean Unicode, far better than the gibberish text-layer fallback for
    # the WHOLE doc), but surface it LOUDLY — a silently short paper is the one
    # failure mode we must never hide. tasks.py logs question counts alongside.
    if state == "PartiallyCompleted":
        print(f"  [sarvam-vision] WARNING: job {job_id} PartiallyCompleted — some "
              f"pages may be missing from the OCR output. Question count may be low.",
              file=sys.stderr)

    # 6. download links. download_urls is a dict {filename: {file_url, ...}} and
    #    the real output is a single ZIP ("document.zip") containing the OCR text
    #    files (md/html/txt/json) — NOT loose files. (Verified against the live API.)
    d = client.post(f"{BASE_URL}/{job_id}/download-files", headers=_headers(key))
    d.raise_for_status()
    download_urls = d.json().get("download_urls", {})

    # normalise to (name, url) pairs whether dict-of-dicts or dict-of-strings
    files = []
    if isinstance(download_urls, dict):
        for name, meta in download_urls.items():
            url = meta.get("file_url") if isinstance(meta, dict) else meta
            if url:
                files.append((name, url))
    if not files:
        raise RuntimeError(f"Sarvam Vision job {job_id} returned no download URLs")

    md_parts = []
    for name, url in files:
        lname = name.lower()
        if lname.endswith(".zip"):
            blob = client.get(url)
            blob.raise_for_status()
            md_parts.extend(_text_from_zip(blob.content))
        elif lname.endswith((".md", ".txt", ".json", ".html")):
            got = client.get(url)
            got.raise_for_status()
            md_parts.append(got.text)
        # ignore .pdf (the re-rendered source) and anything else

    md_parts = [p for p in md_parts if p and p.strip()]
    if not md_parts:
        raise RuntimeError(f"Sarvam Vision job {job_id} produced no text output")
    return "\n".join(md_parts)


def _html_to_text(s: str) -> str:
    """Strip Sarvam's HTML wrapper to plain text. The OCR output wraps content in
    <table>/<tr>/<td>/<br> markup; feeding that raw to the question extractor
    bloats it (~80k chars vs ~30k of real text) and adds noise. Convert row/cell/
    break tags to whitespace, drop the rest, and unescape entities — the
    Devanagari is already clean Unicode."""
    import html as _html
    import re as _re
    # turn structural tags into line/space breaks so question boundaries survive
    s = _re.sub(r"(?i)<\s*br\s*/?>", "\n", s)
    s = _re.sub(r"(?i)</\s*(tr|p|div|h[1-6]|li)\s*>", "\n", s)
    s = _re.sub(r"(?i)</\s*(td|th)\s*>", "  ", s)
    s = _re.sub(r"(?s)<[^>]+>", "", s)        # drop all remaining tags
    s = _html.unescape(s)
    # collapse the blank-line explosion the table stripping leaves behind
    s = _re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _text_from_zip(zip_bytes: bytes) -> list[str]:
    """Pull text out of the Sarvam output ZIP, in page order, HTML stripped to
    plain readable text (Devanagari is already clean Unicode here)."""
    import zipfile
    parts = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = sorted(n for n in zf.namelist()
                       if n.lower().endswith((".md", ".txt", ".html", ".json")))
        # prefer md/txt/html over json if both exist; json is the structured dump
        preferred = [n for n in names if not n.lower().endswith(".json")] or names
        for n in preferred:
            try:
                raw = zf.read(n).decode("utf-8", "replace")
                parts.append(_html_to_text(raw) if n.lower().endswith(".html") else raw)
            except Exception:
                pass
    return parts


def _digitize_chunks(chunks: list[Path], language: str, key: str) -> str:
    """OCR every chunk on ONE key. Raises if the key is dead (credits/auth) so
    the pool can rotate; salvages per-chunk on non-key errors (bad page)."""
    texts, failed = [], 0
    with _client() as client:
        for i, chunk in enumerate(chunks, 1):
            print(f"  [sarvam-vision] OCR chunk {i}/{len(chunks)} ({chunk.name})...",
                  file=sys.stderr)
            try:
                texts.append(_digitize_one(chunk, client, language, key))
            except Exception as e:
                # A dead-key error means EVERY chunk on this key will fail — bubble
                # up so digitize_to_text rotates to the next key instead of
                # burning all chunks. A non-key error (one bad page) is salvaged.
                if _is_key_dead(e):
                    raise
                failed += 1
                print(f"  [sarvam-vision] WARNING: chunk {i}/{len(chunks)} failed "
                      f"({type(e).__name__}: {e}); keeping the other chunks.",
                      file=sys.stderr)
    if not texts:
        raise RuntimeError("Sarvam Vision: all OCR chunks failed")
    if failed:
        print(f"  [sarvam-vision] WARNING: {failed}/{len(chunks)} chunk(s) failed — "
              f"the output paper may be missing those pages' questions.",
              file=sys.stderr)
    return "\n".join(texts)


def digitize_to_text(src: Path, language: str = "hi-IN") -> str:
    """Public entry: any uploaded doc -> clean Unicode text via Sarvam Vision.

    Converts .docx -> PDF, splits to <=10-page chunks, OCRs each, concatenates.
    Tries each key in the POOL in turn: if a key is exhausted (out of credits /
    auth / rate), rotate to the next; only when ALL keys are dead do we raise so
    the caller can fall back to Claude Vision.
    """
    ext = src.suffix.lower()
    if ext == ".docx":
        pdf = _docx_to_pdf(src)
    elif ext == ".pdf":
        pdf = src
    elif ext in (".png", ".jpg", ".jpeg"):
        pdf = None  # single image, handled below
    else:
        raise ValueError(f"Sarvam Vision: unsupported input {src.name}")

    chunks = [src] if pdf is None else _split_pdf(pdf)

    keys = _keys()
    last_err: Exception | None = None
    for idx, key in enumerate(keys, 1):
        try:
            if len(keys) > 1:
                print(f"  [sarvam-vision] trying key {idx}/{len(keys)} "
                      f"(...{key[-4:]})", file=sys.stderr)
            return _digitize_chunks(chunks, language, key)
        except Exception as e:
            last_err = e
            if _is_key_dead(e) and idx < len(keys):
                print(f"  [sarvam-vision] key {idx}/{len(keys)} exhausted "
                      f"({type(e).__name__}: {str(e)[:120]}); rotating to next key",
                      file=sys.stderr)
                continue
            # non-key error, or the last key — stop rotating.
            raise
    # exhausted every key
    raise RuntimeError(f"Sarvam Vision: all {len(keys)} key(s) failed; "
                       f"last error: {last_err}")
