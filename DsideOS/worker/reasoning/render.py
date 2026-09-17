# -*- coding: utf-8 -*-
"""render — the ONLY part of worker/reasoning that touches disk.

Generators return a `_figure` SPEC and nothing else; this turns specs into PNGs
under the job's input directory and rewrites them as `q["image"]`, which is the
key pipeline/build_paper.py:285-286 renders.

WHY IT RAISES INSTEAD OF SKIPPING. pipeline/run_pipeline.py:130-141 checks that
every referenced image EXISTS and, if not, DROPS the question (`:148-158`) and
ships the rest. So a figure that silently fails to write produces a short paper
with no error anywhere — 97 questions instead of 100, cause unknown. This
module therefore verifies every write and raises `FigureError` on the first
failure, converting a silent shortfall into a loud one at generation time,
which is the whole reason figure rendering was split out of the generators.

PATHS. build_paper._IMG_BASE is the directory holding questions.json
(build_paper.py:343), which for a job is storage/jobs/<job_id>/input/
(tasks.py:342). References must be RELATIVE to it and must not escape it —
both build_paper._img_path and run_pipeline.validate enforce that. We write
into a `figs/` subfolder, following crop_figure.py's own `crops/qN-figure.png`
convention.

Interface:
    render_all(questions, out_dir) -> int      # figures written
    FigureError
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Subfolder under the job's input dir. Mirrors crop_figure.py's `crops/`.
FIG_DIR = "figs"


class FigureError(RuntimeError):
    """A figure could not be rendered or written.

    Deliberately fatal: the alternative is a question silently dropped from
    the finished paper (see the module docstring).
    """


def render_all(questions: list[dict], out_dir: Path | str) -> int:
    """Render every `_figure` spec to a PNG and rewrite it as `q["image"]`.

    Mutates `questions` in place:
      - writes `<out_dir>/figs/q<n>.png`
      - sets `q["image"] = "figs/q<n>.png"`   (relative, as the builder needs)
      - deletes `q["_figure"]`                 (internal, must not reach JSON)

    Questions with no `_figure` are untouched, so a mixed block of text and
    figure questions passes through safely.

    Returns the number of figures written.

    Complexity: O(questions) renders, each O(canvas). A 10-question block with
    ~3 figures takes well under a second.

    Raises FigureError if ANY figure fails — never partially succeeds quietly.
    """
    # Imported here, not at module scope: worker/reasoning/__init__.py imports
    # every generator at package import, and nothing should pull Pillow in
    # until a figure is actually being drawn.
    from . import figures

    out = Path(out_dir)
    fig_dir = out / FIG_DIR
    written = 0

    for i, q in enumerate(questions, 1):
        # OPTION IMAGES first — a question has either one stem figure or four
        # option figures, never both. build_paper.py:289-294 renders
        # option_images INSTEAD of text options, so all four must exist or the
        # question is unanswerable.
        opt_specs = q.get("_figure_options")
        if opt_specs:
            num = q.get("n", i)
            rels = []
            for j, spec in enumerate(opt_specs):
                rel = f"{FIG_DIR}/q{num}{chr(97 + j)}.png"
                dest = fig_dir / f"q{num}{chr(97 + j)}.png"
                try:
                    fig_dir.mkdir(parents=True, exist_ok=True)
                    figures.draw(spec).save(dest, "PNG")
                except Exception as e:                   # noqa: BLE001
                    raise FigureError(
                        f"question {num} ({q.get('_type')}): option figure "
                        f"{j} failed -> {e}. The question would be DROPPED by "
                        f"run_pipeline.validate."
                    ) from e
                if not dest.exists() or dest.stat().st_size == 0:
                    raise FigureError(
                        f"question {num}: option figure {j} wrote no bytes")
                rels.append(rel)
            q["option_images"] = rels
            q.pop("_figure_options", None)
            written += len(rels)
            continue

        spec = q.get("_figure")
        if not spec:
            continue

        # `n` is assigned by generate.py AFTER this runs in some call orders,
        # so fall back to the loop index — the filename only has to be unique
        # within the job.
        num = q.get("n", i)
        rel = f"{FIG_DIR}/q{num}.png"
        dest = fig_dir / f"q{num}.png"

        try:
            fig_dir.mkdir(parents=True, exist_ok=True)
            img = figures.draw(spec)
            img.save(dest, "PNG")
        except Exception as e:                       # noqa: BLE001 — see below
            raise FigureError(
                f"question {num} ({q.get('_type')}): could not render its "
                f"figure -> {e}. The question would be DROPPED by "
                f"run_pipeline.validate and the paper would ship short."
            ) from e

        if not dest.exists() or dest.stat().st_size == 0:
            raise FigureError(
                f"question {num} ({q.get('_type')}): figure wrote no bytes to "
                f"{dest}")

        q["image"] = rel
        q.pop("_figure", None)
        written += 1

    if written:
        logger.info("reasoning: rendered %d figure(s) into %s", written, fig_dir)
    return written


def strip_specs(questions: list[dict]) -> None:
    """Drop `_figure` from every question, for callers that cannot render.

    Used when no output directory is available (a preview, a test, a caller
    that only wants the text). The question stays valid — it just loses its
    diagram — which is the right degradation for a type whose stem already
    describes the figure in words.
    """
    for q in questions:
        q.pop("_figure", None)
        q.pop("_figure_options", None)
