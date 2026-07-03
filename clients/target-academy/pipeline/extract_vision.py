# -*- coding: utf-8 -*-
"""Vision question extractor — phone photos and (scanned/image) PDFs.

The zero-friction input path for the app: a user photographs a textbook page or
uploads a scanned PDF, and this turns it into the universal questions JSON that
run_pipeline.py consumes. No manual transcription.

    image(s)  ─┐
    PDF page ──┼─► Claude Vision (one message, all pages) ─► {"questions":[...]}
    ───────────┘

PDF pages are rasterised with PyMuPDF (fitz) at 150 dpi — the same render path
crop_figure.py already uses. Images are sent as-is. Multiple inputs are batched
into a single multimodal message so questions spanning two photos still join up.

Output text is transcribed in WHATEVER script the source uses (Devanagari /
Latin). Unlike the legacy-font .docx path, a photo is real Unicode — so this
emits Unicode Devanagari, which the builders' unicode_to_krutidev path handles.

Usage:
    python extract_vision.py page1.jpg page2.jpg          # -> stdout
    python extract_vision.py scan.pdf -o review/input/x.json
    python extract_vision.py *.jpg --dpi 200 -o out.json
"""
import argparse
import base64
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# Vision is Claude-first (image message shape is Anthropic-specific). It pins the
# smart Anthropic model directly rather than the provider-routed tier.
from llm import MODELS, client, message_text, parse_json  # noqa: E402

MODEL = MODELS["anthropic"]["smart"]


class VisionTruncated(Exception):
    """Raised when a Vision extraction hit the output-token cap (the JSON was cut
    off). Carries the complete questions we salvaged so the caller can re-batch the
    remaining pages instead of losing the whole batch."""
    def __init__(self, message: str, salvaged: list | None = None):
        super().__init__(message)
        self.salvaged = salvaged or []


IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DEFAULT_DPI = 150
MAX_IMAGES = 20          # Anthropic per-request image cap territory; refuse beyond
MAX_DIM = 1568           # Anthropic downsizes above this anyway; pre-shrink to save tokens

SYSTEM = """You read photographed or scanned exam-paper pages and extract every \
multiple-choice question into clean structured JSON. Pages may be bilingual \
(English/Hindi in Devanagari script), slightly skewed, or low-contrast — do your \
best to read accurately. Transcribe text in its ORIGINAL script verbatim; do not \
translate or transliterate. Keep English words in English.

Identify each numbered question, its stem, and its options. Option markers vary \
— (a)/(A)/1)/i. etc. Strip the marker; keep the option body verbatim. Ignore \
section headers, instructions, page numbers, and watermarks. If a question is \
cut off at a page edge, include what is visible and add "flag":"partial".

Return ONLY a JSON object, no prose:
{"questions":[
  {"n":1,"stem":"<verbatim stem>","options":["<opt1>","<opt2>","<opt3>","<opt4>"],
   "answer":"a"}
]}
Rules:
- "n": question number as printed (integer). If unnumbered, number sequentially.
- "stem"/"options": verbatim, marker stripped, order preserved (2-6 options).
- "answer": ONLY if an answer key is visibly printed on the page (lowercase
  letter). If not shown, OMIT — never guess from the page.
- A diagram-only option that cannot be transcribed as text: set the option to
  "[diagram]" and add "flag":"has_diagram" on that question for manual handling.
- Skip anything that is not an actual question."""

USER_TEXT = ("Extract every MCQ from these page image(s), in reading order. "
             "Return the JSON object only.")


def _png_b64(img) -> str:
    """PIL image -> base64 PNG, downsized so the long edge <= MAX_DIM."""
    from PIL import Image
    if max(img.size) > MAX_DIM:
        img = img.copy()
        img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _image_blocks(paths: list[Path], dpi: int) -> list[dict]:
    """Turn input files (images and/or PDFs) into Anthropic image content blocks."""
    from PIL import Image
    blocks: list[dict] = []
    for p in paths:
        ext = p.suffix.lower()
        if ext == ".pdf":
            import fitz
            doc = fitz.open(str(p))
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            for page in doc:
                pix = page.get_pixmap(matrix=mat)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                blocks.append(_block(_png_b64(img)))
            doc.close()
        elif ext in IMG_EXT:
            with Image.open(p) as img:
                blocks.append(_block(_png_b64(img)))
        else:
            raise ValueError(f"Unsupported input: {p.name} (need image or .pdf)")
        if len(blocks) > MAX_IMAGES:
            raise ValueError(
                f"{len(blocks)} pages exceeds the {MAX_IMAGES}-image cap for one "
                f"request. Split the input or extract in batches."
            )
    return blocks


def _block(b64: str) -> dict:
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64}}


def extract(paths: list[Path], dpi: int = DEFAULT_DPI) -> dict:
    """Read image/PDF page(s) and return {"questions": [...]} via Claude Vision."""
    blocks = _image_blocks(paths, dpi)
    if not blocks:
        raise ValueError("No pages to read.")
    content = [{"type": "text", "text": USER_TEXT}] + blocks
    msg = client().messages.create(
        model=MODEL,
        max_tokens=16_000,
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    raw = message_text(msg)

    # Truncation guard: if the output hit the token cap the JSON array is cut off
    # mid-way, so parse_json would either raise or silently return a PARTIAL set —
    # shipping fewer questions than the pages held, with no error. Salvage whatever
    # complete objects we can, then RAISE so the caller (tasks._claude_vision_extract)
    # re-batches with fewer pages rather than accepting a short paper.
    truncated = getattr(msg, "stop_reason", None) == "max_tokens"
    try:
        data = parse_json(raw)
        if isinstance(data, list):
            data = {"questions": data}
    except (ValueError, Exception):
        data = {"questions": []}
    if truncated or not data.get("questions"):
        # recover complete objects from the (possibly truncated) array
        try:
            import extract_docx
            salvaged = extract_docx._salvage_questions(extract_docx._clean_raw(raw))
        except Exception:
            salvaged = []
        if truncated:
            raise VisionTruncated(
                f"Claude Vision output hit the {16_000}-token cap "
                f"(recovered {len(salvaged)} complete question(s)); "
                f"caller should re-batch with fewer pages.", salvaged)
        if salvaged:
            return {"questions": salvaged}
        raise ValueError("Claude returned no questions.")
    return data


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(
        description="Extract MCQs from photos or scanned/image PDFs via Claude Vision.")
    ap.add_argument("inputs", nargs="+", type=Path, help="image and/or PDF files")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="PDF render dpi (default 150)")
    ap.add_argument("-o", "--out", type=Path, help="write JSON here (else stdout)")
    args = ap.parse_args()

    import json
    data = extract(args.inputs, dpi=args.dpi)
    n = len(data["questions"])
    with_ans = sum(1 for q in data["questions"] if q.get("answer"))
    flagged = [q["n"] for q in data["questions"] if q.get("flag")]
    text = json.dumps(data, ensure_ascii=False, indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"OK: {n} questions ({with_ans} with printed answers) -> {args.out}")
    else:
        print(text)
        print(f"\n# {n} questions, {with_ans} with printed answers", file=sys.stderr)
    if flagged:
        print(f"# flagged for manual check: Q {flagged}", file=sys.stderr)


if __name__ == "__main__":
    main()
