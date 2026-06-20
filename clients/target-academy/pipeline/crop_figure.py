"""Crop diagram regions out of a rendered exam-paper page, verbatim.

Reasoning/maths questions carry figures that cannot be retyped (triangle-count
shapes, figure-analogy diagrams, matchstick puzzles). For those we embed the
ACTUAL pixels from the paper — text stays branded (Kruti Dev), only the diagram
is a crop.

Workflow during a live run:
  1. fitz renders each page to resources/live_pages/page_NN.png (dpi=150).
  2. For each diagram question, identify the box (left, top, right, bottom) in
     pixels on that page PNG — read off the rendered image.
  3. crop(page_png, box, out_png) writes the crop into review/input/crops/.
  4. The questions JSON references it: "image": "crops/q3-figure.png" (path is
     relative to the JSON's own folder).

The paper is bilingual (English left half / Hindi right half). Target Academy
is all-Hindi, so crop the RIGHT-column figure. page_right_half() helps locate it.

Usage (programmatic, from the live-run flow):
    from crop_figure import crop
    crop("resources/live_pages/page_03.png", (640, 250, 1180, 720),
         "review/input/crops/q3-figure.png")
"""

import sys
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parents[1]


def crop(page_png, box, out_png, pad=6):
    """Crop `box`=(left,top,right,bottom) px from page_png → out_png (PNG).

    `pad` adds a small white-safe margin so figure strokes aren't clipped.
    Returns the output Path. Box is clamped to the image bounds.
    """
    img = Image.open(page_png).convert("RGB")
    w, h = img.size
    left, top, right, bottom = box
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(w, right + pad)
    bottom = min(h, bottom + pad)
    if right <= left or bottom <= top:
        raise ValueError(f"degenerate crop box {box} on {w}x{h} image")
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.crop((left, top, right, bottom)).save(out, "PNG")
    return out


def page_right_half(page_png):
    """(width, height, x_mid) for a page — the Hindi column starts near x_mid."""
    img = Image.open(page_png)
    w, h = img.size
    return w, h, w // 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    # Quick CLI: python crop_figure.py page.png L T R B out.png
    if len(sys.argv) == 7:
        pg, l, t, r, b, out = sys.argv[1:]
        p = crop(pg, (int(l), int(t), int(r), int(b)), out)
        print(f"OK: {p} ({Image.open(p).size[0]}x{Image.open(p).size[1]})")
    else:
        # default: report page geometry for live_pages/
        pages = sorted((BASE / "resources" / "live_pages").glob("page_*.png"))
        if pages:
            w, h, mid = page_right_half(pages[0])
            print(f"{len(pages)} pages, {w}x{h}px each, Hindi column x>={mid}")
        else:
            print("no rendered pages found in resources/live_pages/")
