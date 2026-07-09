# -*- coding: utf-8 -*-
"""Generic question extractor for ANY PDF exam paper.

PDFs come in two kinds and the right handling differs:

  - DIGITAL  (exported from Word/LaTeX): has a real text layer. Pull the text
    with PyMuPDF and route it through the shared text extractor — cheap, no
    vision tokens.
  - SCANNED / IMAGE (photographed, scanned, or flattened): no usable text layer.
    Render each page to an image and route through Claude Vision.

This script AUTO-DETECTS which kind it is (per the average text yield per page)
and picks the path — so one command handles both. Force either path with
--mode text|vision if the heuristic guesses wrong.

    digital PDF ──► fitz text  ──► extract_docx.extract_from_text ──┐
                                                                     ├─► JSON
    scanned PDF ──► fitz render ─► extract_vision.extract ──────────┘

Usage:
    python extract_pdf.py paper.pdf                       # auto-detect -> stdout
    python extract_pdf.py paper.pdf -o review/input/x.json
    python extract_pdf.py scan.pdf --mode vision --dpi 200 -o x.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import extract_docx    # noqa: E402  (shared text path)
import extract_vision  # noqa: E402  (vision path)

# Below this many extractable chars-per-page on average, treat the PDF as
# scanned and fall back to vision. The two populations are far apart — a digital
# paper yields hundreds/page, a scanned one yields ~0 (maybe a little OCR noise)
# — so a low bar separates them cleanly. The text path is also self-correcting:
# if it finds no text after routing, extract() fails over to vision anyway.
TEXT_CHARS_PER_PAGE_MIN = 25


def pdf_text(path: Path) -> tuple[str, int]:
    """Extract the text layer with PyMuPDF. Returns (joined_text, page_count)."""
    import fitz
    doc = fitz.open(str(path))
    parts = []
    for page in doc:
        t = page.get_text("text").strip()
        if t:
            parts.append(t)
    n = doc.page_count
    doc.close()
    return "\n".join(parts), n


def detect_mode(path: Path) -> tuple[str, str]:
    """Decide 'text' vs 'vision'. Returns (mode, reason)."""
    text, n_pages = pdf_text(path)
    per_page = len(text) / max(n_pages, 1)
    if per_page >= TEXT_CHARS_PER_PAGE_MIN:
        return "text", f"{int(per_page)} chars/page — digital PDF, text layer present"
    return "vision", f"{int(per_page)} chars/page — looks scanned/image, using vision"


def extract(path: Path, mode: str = "auto", dpi: int = extract_vision.DEFAULT_DPI) -> dict:
    """Extract questions from a PDF, auto-routing digital vs scanned."""
    if mode == "auto":
        mode, reason = detect_mode(path)
        print(f"detect: {reason} -> {mode} path", file=sys.stderr)

    if mode == "text":
        body, _ = pdf_text(path)
        if not body.strip():
            # Heuristic said text but there is none — fail over to vision.
            print("detect: no text after all, falling back to vision",
                  file=sys.stderr)
            return extract_vision.extract([path], dpi=dpi)
        # A digital PDF's text layer is Kruti-Dev-encoded (same as the .docx text
        # layer) when the source used a Kruti-Dev font — flag it so the extractor
        # transliterates rather than treating garbled ASCII as clean Unicode. (The
        # clean path is Sarvam Vision / the scanned-PDF vision route below.)
        return extract_docx.extract_from_text(body, label=path.name,
                                              krutidev_input=True)

    if mode == "vision":
        return extract_vision.extract([path], dpi=dpi)

    raise ValueError(f"unknown mode: {mode!r} (use auto|text|vision)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Extract MCQs from any PDF (digital or scanned).")
    ap.add_argument("pdf", type=Path, help="path to the .pdf exam paper")
    ap.add_argument("--mode", choices=["auto", "text", "vision"], default="auto",
                    help="extraction path (default auto-detect)")
    ap.add_argument("--dpi", type=int, default=extract_vision.DEFAULT_DPI,
                    help="render dpi for the vision path (default 150)")
    ap.add_argument("-o", "--out", type=Path, help="write JSON here (else stdout)")
    args = ap.parse_args()

    data = extract(args.pdf, mode=args.mode, dpi=args.dpi)
    n = len(data["questions"])
    with_ans = sum(1 for q in data["questions"] if q.get("answer"))
    text = json.dumps(data, ensure_ascii=False, indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"OK: {n} questions ({with_ans} with printed answers) -> {args.out}")
    else:
        print(text)
        print(f"\n# {n} questions, {with_ans} with printed answers", file=sys.stderr)


if __name__ == "__main__":
    main()
