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


def _key() -> str:
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        raise RuntimeError("SARVAM_API_KEY not set (required for Sarvam Vision).")
    return key


def _headers() -> dict:
    return {"api-subscription-key": _key()}


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


def _digitize_one(pdf: Path, client: httpx.Client, language: str) -> str:
    """Run one <=10-page PDF through the Sarvam Vision job flow -> markdown text."""
    # 1. create job
    r = client.post(BASE_URL, headers=_headers(),
                    json={"job_parameters": {"language": language, "output_format": "md"}})
    r.raise_for_status()
    job_id = r.json()["job_id"]

    # 2. get the presigned upload URL for our file
    r = client.post(f"{BASE_URL}/upload-files", headers=_headers(),
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

    # 4. start
    client.post(f"{BASE_URL}/{job_id}/start", headers=_headers()).raise_for_status()

    # 5. poll status
    deadline = POLL_TIMEOUT_S / POLL_INTERVAL_S
    state = "Accepted"
    for _ in range(int(deadline) + 1):
        s = client.get(f"{BASE_URL}/{job_id}/status", headers=_headers())
        s.raise_for_status()
        state = s.json().get("job_state", "")
        if state in _TERMINAL_OK or state in _TERMINAL_BAD:
            break
        time.sleep(POLL_INTERVAL_S)
    if state in _TERMINAL_BAD or state not in _TERMINAL_OK:
        raise RuntimeError(f"Sarvam Vision job {job_id} ended in state {state!r}")

    # 6. download links
    d = client.post(f"{BASE_URL}/{job_id}/download-files", headers=_headers())
    d.raise_for_status()
    download_urls = d.json().get("download_urls", {})

    # 7. fetch the markdown output (prefer .md, else any non-pdf text file)
    md_parts = []
    for name, meta in download_urls.items():
        url = meta.get("file_url") if isinstance(meta, dict) else meta
        if not url or name.lower().endswith(".pdf"):
            continue
        if name.lower().endswith((".md", ".txt", ".json", ".html")):
            got = client.get(url)
            got.raise_for_status()
            md_parts.append(got.text)
    if not md_parts:
        raise RuntimeError(f"Sarvam Vision job {job_id} produced no text output")
    return "\n".join(md_parts)


def digitize_to_text(src: Path, language: str = "hi-IN") -> str:
    """Public entry: any uploaded doc -> clean Unicode text via Sarvam Vision.

    Converts .docx -> PDF, splits to <=10-page chunks, OCRs each, concatenates.
    Raises on any failure so the caller can fall back to the text-layer path.
    """
    ext = src.suffix.lower()
    if ext == ".docx":
        pdf = _docx_to_pdf(src)
    elif ext == ".pdf":
        pdf = src
    elif ext in (".png", ".jpg", ".jpeg"):
        # images go straight in (single "page")
        with _client() as client:
            return _digitize_one(src, client, language)
    else:
        raise ValueError(f"Sarvam Vision: unsupported input {src.name}")

    chunks = _split_pdf(pdf)
    texts = []
    with _client() as client:
        for i, chunk in enumerate(chunks, 1):
            print(f"  [sarvam-vision] OCR chunk {i}/{len(chunks)} ({chunk.name})...",
                  file=sys.stderr)
            texts.append(_digitize_one(chunk, client, language))
    return "\n".join(texts)
