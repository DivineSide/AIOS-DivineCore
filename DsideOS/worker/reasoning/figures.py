# -*- coding: utf-8 -*-
"""figures — turn a figure SPEC into a PIL image. No file I/O, no job state.

THE SPLIT THIS MODULE EXISTS FOR: a reasoning generator stays PURE — it returns
a question dict plus a `_figure` spec DESCRIBING the drawing, never a file. This
module turns a spec into an in-memory image; `render.py` is the only thing that
touches disk.

Three reasons that split earns its keep:
  - figure logic is testable at 1000 seeds/second with no temp directories
  - a drawing bug fails HERE, it cannot corrupt a question's answer
  - every spec can be confirmed rendered BEFORE the paper is built, which is
    the only defence against run_pipeline.py:130-141 — a missing PNG silently
    DROPS the question and ships a short paper rather than erroring

RENDERING: Pillow only. matplotlib, cairo, svglib and reportlab are absent from
this environment AND from worker/requirements.txt, which is everything the
Docker image installs (worker/Dockerfile:20-21). Pillow is already a dependency
(build_paper.py:30 imports it), so figures add nothing new.

SUPERSAMPLING: ImageDraw has no antialiasing. Everything is drawn at SS× the
target size and downsampled with LANCZOS, which is the standard trick and the
only way thin diagonal lines look like exam print rather than staircases.

Interface:
    draw(spec) -> PIL.Image          # spec is a plain dict, JSON-serialisable
    font(size)  -> ImageFont         # portable resolution, see _FONT_CANDIDATES
"""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

# Target pixel size before supersampling. The paper box is 4.8 x 4.0 cm
# (build_paper.STEM_FIG_W_CM/H_CM); at ~150 dpi that is ~283 x 236 px, so 320
# gives a little headroom without bloating the .docx.
SIZE = 320
SS = 3                     # supersample factor — 3x is the quality/size knee
LINE = 2                   # stroke width at final size; scaled by SS when drawn
INK = (0, 0, 0)
PAPER = (255, 255, 255)

# FONT PORTABILITY — a real trap, not a theoretical one. Local Windows has
# arial.ttf; the container does NOT. worker/Dockerfile installs fonts-deva and
# fonts-lohit-deva (Devanagari) plus bundled licensed fonts under
# /usr/share/fonts/truetype/dsideos/, but guarantees no LATIN TTF — and dice
# digits are Latin. So: try a documented chain, end at Pillow's built-in bitmap
# font, and NEVER hardcode a single path.
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/dsideos/NirmalaUI.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


@lru_cache(maxsize=16)
def font(size: int):
    """A usable font at `size`, or Pillow's bitmap default.

    Cached because ImageFont.truetype re-reads the file every call and a dice
    figure asks for the same size nine times.

    Never raises: a figure with ugly digits still ships; a figure that throws
    would drop the question (see the module docstring).
    """
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (SIZE * SS, SIZE * SS), PAPER)
    return img, ImageDraw.Draw(img)


def _finish(img: Image.Image) -> Image.Image:
    """Crop to the ink, add a small margin, then downsample.

    Cropping matters for LAYOUT, not looks: build_paper.add_figure fits the
    image into a 4.8 x 4.0 cm box by ASPECT RATIO, so dead white space around
    the drawing shrinks the drawing itself. A wide strip of triangles and a
    square dial should each fill the box in their own proportion.

    LANCZOS on the downsample is what makes thin diagonals read as print
    rather than staircases — ImageDraw has no antialiasing of its own.
    """
    bbox = img.convert("L").point(lambda v: 0 if v > 250 else 255).getbbox()
    if bbox:
        pad = int(SIZE * SS * 0.04)
        img = img.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                        min(img.width, bbox[2] + pad),
                        min(img.height, bbox[3] + pad)))
    w, h = img.size
    scale = SIZE / max(w, h)
    return img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                      Image.LANCZOS)


def _centred_text(d: ImageDraw.ImageDraw, xy, text: str, size: int) -> None:
    """Draw `text` centred on `xy`, in supersampled coordinates."""
    f = font(size * SS)
    try:
        box = d.textbbox((0, 0), text, font=f)
        w, h = box[2] - box[0], box[3] - box[1]
        d.text((xy[0] - w / 2 - box[0], xy[1] - h / 2 - box[1]),
               text, fill=INK, font=f)
    except Exception:                       # pragma: no cover — bitmap fallback
        d.text(xy, text, fill=INK, font=f, anchor="mm")


# ── dice ────────────────────────────────────────────────────────────────────

def _draw_dice(spec: dict) -> Image.Image:
    """Three isometric cubes side by side, each showing top/left/right.

    Matches the real paper's shape (see
    corpus/reasoning-reference/vdo-vpdo-2023-07-09/page5.png): a hexagon
    outline with three internal edges meeting at the centre, one digit per
    visible face.

    spec["views"] is [(top, left, right), ...].
    """
    views = spec["views"]
    n = len(views)
    img, d = _canvas()
    W = SIZE * SS

    # Lay the cubes out across the width with gaps; each cube is a hexagon of
    # circumradius r.
    slot = W / n
    r = min(slot * 0.36, W * 0.16)
    cy = W * 0.45
    lw = LINE * SS

    for i, (top, left, right) in enumerate(views):
        cx = slot * (i + 0.5)
        # Hexagon vertices, flat-top isometric cube silhouette: start at the
        # top vertex and step 60 degrees.
        pts = [(cx + r * math.cos(math.radians(a)),
                cy + r * math.sin(math.radians(a)))
               for a in (-90, -30, 30, 90, 150, 210)]
        d.polygon(pts, outline=INK, width=lw)
        # The three internal edges: centre to the alternating vertices. This is
        # what reads as "cube" rather than "hexagon".
        for v in (pts[1], pts[3], pts[5]):
            d.line([(cx, cy), v], fill=INK, width=lw)

        # Face centroids: each visible face is a rhombus between two hexagon
        # vertices and the centre. Averaging the three corners puts the digit
        # where the eye expects it.
        fs = max(11, int(r / SS * 0.42))
        _centred_text(d, ((cx + pts[5][0] + pts[0][0] + pts[1][0]) / 4,
                          (cy + pts[5][1] + pts[0][1] + pts[1][1]) / 4),
                      str(top), fs)
        _centred_text(d, ((cx + pts[3][0] + pts[4][0] + pts[5][0]) / 4,
                          (cy + pts[3][1] + pts[4][1] + pts[5][1]) / 4),
                      str(left), fs)
        _centred_text(d, ((cx + pts[1][0] + pts[2][0] + pts[3][0]) / 4,
                          (cy + pts[1][1] + pts[2][1] + pts[3][1]) / 4),
                      str(right), fs)

        # Roman numeral under each cube, as the real papers label them.
        _centred_text(d, (cx, cy + r * 1.45), ["I", "II", "III", "IV"][i],
                      max(10, int(r / SS * 0.30)))

    return _finish(img)


# ── line figures (triangle / square counting) ───────────────────────────────

def _draw_lines(spec: dict) -> Image.Image:
    """Plain line art from a list of segments in unit coordinates.

    spec["segments"] is [((x0,y0),(x1,y1)), ...] with coordinates in [0,1];
    this maps them into the canvas with a margin. Keeping the spec in unit
    space means the GEOMETRY (which is what the answer is computed from) never
    depends on pixel size.
    """
    img, d = _canvas()
    W = SIZE * SS
    m = W * 0.10                            # margin
    span = W - 2 * m
    lw = LINE * SS

    for (x0, y0), (x1, y1) in spec["segments"]:
        d.line([(m + x0 * span, m + y0 * span),
                (m + x1 * span, m + y1 * span)], fill=INK, width=lw)
    return _finish(img)


# ── clock ───────────────────────────────────────────────────────────────────

def _draw_clock(spec: dict) -> Image.Image:
    """A clock dial showing spec["hour"]:spec["minute"].

    Drawn as a real dial — circle, twelve tick marks, hour and minute hands —
    because the question asks what the FACE looks like reflected. A digital
    time would make the question meaningless.
    """
    h, m = spec["hour"], spec["minute"]
    img, d = _canvas()
    W = SIZE * SS
    cx = cy = W / 2
    r = W * 0.38
    lw = LINE * SS

    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INK, width=lw)

    for t in range(12):
        a = math.radians(t * 30 - 90)
        inner = r * (0.86 if t % 3 else 0.80)
        d.line([(cx + inner * math.cos(a), cy + inner * math.sin(a)),
                (cx + r * 0.96 * math.cos(a), cy + r * 0.96 * math.sin(a))],
               fill=INK, width=lw if t % 3 else lw * 2)

    # Hour hand advances with the minutes — at 8:30 it sits halfway to 9, which
    # is exactly the detail a reflected-dial question turns on.
    ha = math.radians((h % 12) * 30 + m * 0.5 - 90)
    ma = math.radians(m * 6 - 90)
    d.line([(cx, cy), (cx + r * 0.50 * math.cos(ha), cy + r * 0.50 * math.sin(ha))],
           fill=INK, width=lw * 3)
    d.line([(cx, cy), (cx + r * 0.78 * math.cos(ma), cy + r * 0.78 * math.sin(ma))],
           fill=INK, width=lw * 2)
    d.ellipse([cx - lw * 2, cy - lw * 2, cx + lw * 2, cy + lw * 2], fill=INK)

    return _finish(img)


# ── venn / logic diagrams ───────────────────────────────────────────────────

def _draw_venn(spec: dict) -> Image.Image:
    """Circles laid out to show a set relationship.

    spec["circles"] is [{"cx","cy","r"}, ...] in unit coordinates — the
    GENERATOR decides the geometry, because the geometry IS the answer. This
    function only draws what it is told, which keeps the relationship logic in
    one place and testable without pixels.

    Modelled on vdo-vpdo 2023-07-09 Q27 (see
    corpus/reasoning-reference/vdo-vpdo-2023-07-09/page7.png): two overlapping
    circles plus a detached one, as four option diagrams.
    """
    img, d = _canvas()
    W = SIZE * SS
    m = W * 0.08
    span = W - 2 * m
    lw = LINE * SS

    for c in spec["circles"]:
        cx = m + c["cx"] * span
        cy = m + c["cy"] * span
        r = c["r"] * span
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INK, width=lw)
    return _finish(img)



# ── figure series ───────────────────────────────────────────────────────────

def _draw_symbol(d, name: str, cx: float, cy: float, s: float, lw: int) -> None:
    """One quadrant symbol, centred on (cx, cy) with nominal half-size `s`.

    Drawn as GEOMETRY, never as a text glyph. The container has no guaranteed
    font carrying ○ □ △ (see the font chain above), and a missing glyph renders
    as a blank box — which in this question type would silently destroy the
    very thing being compared.
    """
    if name == "circle":
        d.ellipse([cx - s, cy - s, cx + s, cy + s], outline=INK, width=lw)
    elif name == "square":
        d.rectangle([cx - s, cy - s * 0.82, cx + s, cy + s * 0.82],
                    outline=INK, width=lw)
    elif name == "triangle":
        d.polygon([(cx, cy - s), (cx - s, cy + s), (cx + s, cy + s)],
                  outline=INK, width=lw)
    elif name == "plus":
        d.line([(cx - s, cy), (cx + s, cy)], fill=INK, width=lw)
        d.line([(cx, cy - s), (cx, cy + s)], fill=INK, width=lw)
    else:
        raise KeyError(f"unknown figseries symbol {name!r}")


def _draw_figseries(spec: dict) -> Image.Image:
    """A horizontal strip of squares, each split by BOTH diagonals.

    spec["squares"] is a list of [top, left, right, bottom] symbol names, one
    per square; spec["labels"] is the number printed under each ("" for the
    unnumbered first figure).

    Modelled on vdo-vpdo 2023-07-09 Q22 (page5.png). Aspect is ~5:1, which
    _finish preserves — build_paper fits by aspect, so the strip fills the box
    width and stays readable rather than being squashed into a square.
    """
    squares = spec["squares"]
    labels = spec.get("labels") or [""] * len(squares)

    n = len(squares)
    # WRAP into rows. A single 5-square row is ~3:1, and build_paper caps a stem
    # figure at 4.8cm WIDE (the height cap of 4.0cm never binds), so one row
    # printed 4.8 x 1.6cm — under 1cm per square for four symbols, measured
    # illegible in the first real PDF. Wrapping to 3-per-row roughly doubles the
    # printed square size within the same width budget. Reading order is
    # left-to-right, top-to-bottom, and the numbers under each square keep the
    # sequence unambiguous.
    per_row = 3 if n > 3 else n
    n_rows = (n + per_row - 1) // per_row

    cell = SIZE * SS * 0.9 / per_row
    lw = max(1, int(LINE * SS * 0.7))
    m = cell * 0.18
    label_h = cell * 0.42
    row_h = cell + label_h

    W = int(cell * per_row + 2 * m)
    H = int(row_h * n_rows + 2 * m)
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    for i, quad in enumerate(squares):
        col, row = i % per_row, i // per_row
        x0 = m + col * cell
        y0 = m + row * row_h
        x1, y1 = x0 + cell, y0 + cell
        d.rectangle([x0, y0, x1, y1], outline=INK, width=lw)
        d.line([(x0, y0), (x1, y1)], fill=INK, width=lw)
        d.line([(x1, y0), (x0, y1)], fill=INK, width=lw)

        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        off = cell * 0.29          # centroid of a quadrant triangle, roughly
        s = cell * 0.10
        top, left, right, bottom = quad
        _draw_symbol(d, top, cx, cy - off, s, lw)
        _draw_symbol(d, left, cx - off, cy, s, lw)
        _draw_symbol(d, right, cx + off, cy, s, lw)
        _draw_symbol(d, bottom, cx, cy + off, s, lw)

        if i < len(labels) and labels[i]:
            _centred_text(d, (cx, y1 + label_h * 0.6), str(labels[i]),
                          int(cell / SS * 0.30))

    return _finish(img)

_KINDS = {
    "dice": _draw_dice,
    "lines": _draw_lines,
    "clock": _draw_clock,
    "venn": _draw_venn,
    "figseries": _draw_figseries,
}


def draw(spec: dict) -> Image.Image:
    """Render a figure spec. Raises KeyError on an unknown kind — deliberately
    loud, since a silently-skipped figure becomes a dropped question."""
    kind = spec.get("kind")
    if kind not in _KINDS:
        raise KeyError(f"unknown figure kind {kind!r}; "
                       f"known: {sorted(_KINDS)}")
    return _KINDS[kind](spec)
