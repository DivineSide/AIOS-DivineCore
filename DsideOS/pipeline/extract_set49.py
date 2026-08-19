"""Extract questions from set 49.docx preserving raw Kruti Dev text.

NO Unicode conversion. Text is kept exactly as typed in the source file.
Each question returns:
  {
    "n": int,
    "stem_runs": [(text, font_name), ...],
    "options":   [runs_A, runs_B, runs_C, runs_D]
                 where each runs_X = [(text, font_name), ...]
  }
"""

import re
import sys
from pathlib import Path

from docx import Document

DOCX_PATH = Path(__file__).resolve().parents[3] / "set 49.docx"

KRUTI = "Kruti Dev 010"
LATIN = "Times New Roman"

# ── Option detection ──────────────────────────────────────────────────────────
# Styles found in this file:
#   "¼A½ text"   (most sections)
#   "A½ text"    (history/polity, where ¼ is in a previous run)
#   "C) text"    (typo in one question — ) instead of ½)
_OPT_ANY = re.compile(r"^¼?[ABCDabcd][½)]")


def _is_option_line(text: str) -> bool:
    return bool(_OPT_ANY.match(text))


def _split_options_from_line(para_runs):
    """Split a paragraph containing 2 or 4 inline options into separate run-lists.

    Detects option boundaries by finding run-sequences that start a new option
    label (¼A½ / A½ etc.), then groups subsequent runs until the next label.
    Returns a list of run-lists.
    """
    # Build a flat list with cumulative positions
    full = "".join(t for t, _ in para_runs)

    # Find all option marker spans (¼?[ABCD]½ or [ABCD])
    markers = [m for m in re.finditer(r"¼?[ABCDabcd][½)]\s*", full)]
    if not markers:
        return [para_runs]  # fallback: whole paragraph as one option

    options = []
    for i, m in enumerate(markers):
        body_start = m.end()
        body_end   = markers[i + 1].start() if i + 1 < len(markers) else len(full)
        body_text  = full[body_start:body_end].strip()

        # Determine font: scan runs that overlap the body segment
        seg_font = KRUTI
        pos = 0
        for t, f in para_runs:
            end = pos + len(t)
            if end > body_start and pos < body_end and f == KRUTI:
                seg_font = KRUTI
                break
            pos = end

        if body_text:
            options.append([(body_text, seg_font)])

    return options


# ── Section header detection ──────────────────────────────────────────────────
_IS_SECTION = re.compile(r"^¼.{3,60}vad")


# ── Question number: "101- " or "1. " at paragraph start ─────────────────────
# Also allow leading zero-width space (U+200B) before the number
_Q_NUM_RE = re.compile(r"^[​\s]*(\d+)[.\-]\s*")


def _para_runs(para):
    """Return [(text, font), ...] for every run in the paragraph."""
    runs = []
    for r in para.runs:
        if r.text:
            font = r.font.name if r.font.name else LATIN
            runs.append((r.text, font))
    return runs


def extract(path: Path = DOCX_PATH):
    doc  = Document(str(path))
    paras = doc.paragraphs

    questions = []
    current   = None
    in_stem   = False
    last_n    = 0

    def flush():
        nonlocal current, in_stem
        if current and len(current["options"]) >= 4:
            questions.append({
                "n":         current["n"],
                "stem_runs": current["stem_runs"],
                "options":   current["options"][:4],
            })
        current.__class__  # keep linter happy

    def _flush():
        nonlocal current, in_stem, last_n
        if current and len(current["options"]) >= 4:
            questions.append({
                "n":         current["n"],
                "stem_runs": current["stem_runs"],
                "options":   current["options"][:4],
            })
        current = None
        in_stem = False

    for para in paras:
        text = para.text.strip()
        if not text:
            continue

        # Section headers — skip
        if _IS_SECTION.match(text):
            continue

        # New question?
        m = _Q_NUM_RE.match(text)
        if m:
            n = int(m.group(1))
            if n > last_n:
                _flush()
                last_n = n
                all_runs   = _para_runs(para)
                prefix_len = m.end()

                # Strip the "N- " prefix from runs
                stem_runs = []
                consumed  = 0
                for t, f in all_runs:
                    if consumed >= prefix_len:
                        stem_runs.append((t, f))
                    elif consumed + len(t) <= prefix_len:
                        consumed += len(t)
                    else:
                        leftover = t[prefix_len - consumed:]
                        if leftover:
                            stem_runs.append((leftover, f))
                        consumed = prefix_len

                current = {"n": n, "stem_runs": stem_runs, "options": []}
                in_stem = True
                continue

        if current is None:
            continue

        # Option line?
        if _is_option_line(text):
            in_stem = False
            opts = _split_options_from_line(_para_runs(para))
            current["options"].extend(opts)
            continue

        # Stem continuation
        if in_stem:
            current["stem_runs"].extend(_para_runs(para))

    _flush()
    return questions


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    qs     = extract()
    nums   = {q["n"] for q in qs}
    missing = [n for n in range(1, 141) if n not in nums]
    print(f"Extracted {len(qs)} questions. Missing: {missing}")
    for q in qs[:3]:
        stem = "".join(t for t, _ in q["stem_runs"])
        print(f"\nQ{q['n']}: {stem[:80]}")
        for i, opt_runs in enumerate(q["options"]):
            opt = "".join(t for t, _ in opt_runs)
            print(f"  ({chr(65+i)}) {opt[:60]}")
