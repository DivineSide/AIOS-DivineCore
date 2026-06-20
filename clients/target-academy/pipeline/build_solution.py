"""Build the TEACHER solution doc (.docx) from a solved questions JSON.

Private to the teacher (NOT shown in class) -> no branding, no Kruti Dev: clean
A4 Word in Unicode Devanagari (Nirmala UI). Per question: number + stem, all
options with the correct one bold + ✓, an उत्तर line, and a हल/व्याख्या block
only when the question carries a "solution" field (maths/reasoning/assertion).
Factual GK questions may carry a short "reason" (one line) instead.

Questions JSON shape (per item, superset of build_deck/build_paper):
  { "n", "stem", "statements"?, "match"?, "lead_in"?, "options":[...],
    "answer": "a"|..|"e", "reason"?: "one line", "solution"?: "worked steps" }

Usage: python build_solution.py [questions.json] [out.docx]
"""

import json
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

BASE = Path(__file__).resolve().parents[1]
FONT = "Nirmala UI"          # Unicode Devanagari, ships with Windows
GREEN = RGBColor(0x1B, 0x6B, 0x2D)
GREY = RGBColor(0x55, 0x55, 0x55)
RED = RGBColor(0xC0, 0x2A, 0x2A)
LABELS = ["a", "b", "c", "d", "e", "f"]
FIG_W_CM = 5.0  # teacher doc is single-column; keep figures compact

_IMG_BASE = BASE  # set per build() so JSON image paths resolve beside the JSON


def _img_path(rel):
    p = Path(rel)
    return p if p.is_absolute() else (_IMG_BASE / p)

# Preferred answer sources for national GK; UK-specific questions use ExamPillar + UK sites.
TIER1_SOURCES = ("exampillar", "testbook")


def run(p, text, size=12, bold=False, color=None, italic=False):
    r = p.add_run(text)
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    if color is not None:
        r.font.color.rgb = color
    return r


def tight(p, after=2, before=0):
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.space_before = Pt(before)
    return p


def build(questions_path: Path, out_path: Path):
    global _IMG_BASE
    _IMG_BASE = questions_path.resolve().parent  # crops resolve beside the JSON
    data = json.loads(questions_path.read_text(encoding="utf-8"))
    doc = Document()
    for s in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(doc.sections[0], s, Cm(1.6))
    doc.styles["Normal"].font.name = FONT
    doc.styles["Normal"].font.size = Pt(12)

    title = tight(doc.add_paragraph(), 2)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(title, data.get("solution_title", "समाधान — शिक्षक हेतु (Solution Key)"),
        size=16, bold=True)
    sub = tight(doc.add_paragraph(), 10)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(sub, data.get("solution_subtitle", "केवल शिक्षक के लिए — कक्षा में प्रदर्शित न करें"),
        size=10, color=GREY, italic=True)

    # PYQ papers ship with the commission's official answer key — that IS the
    # source of truth, so no per-question source-checking applies to them.
    official = data.get("answer_source") == "official_key"

    for q in data["questions"]:
        ans_idx = LABELS.index(q["answer"].lower())

        qp = tight(doc.add_paragraph(), 2, before=8)
        run(qp, f"{q['n']}. ", size=12, bold=True)
        run(qp, q["stem"], size=12, bold=True)

        for i, st in enumerate(q.get("statements") or [], start=1):
            run(tight(doc.add_paragraph(), 1), f"   {i}. {st}", size=11)
        for left_t, right_t in q.get("match") or []:
            run(tight(doc.add_paragraph(), 1), f"   {left_t}  —  {right_t}", size=11)
        if q.get("lead_in"):
            run(tight(doc.add_paragraph(), 2), f"   {q['lead_in']}", size=11)

        # the question's own diagram (Q3-type), embedded under the stem
        if q.get("image"):
            fp = tight(doc.add_paragraph(), 4)
            fp.add_run().add_picture(str(_img_path(q["image"])), width=Cm(FIG_W_CM))

        if q.get("option_images"):
            # option diagrams (Q60-type): label, image, ✓ on the correct one
            for i, rel in enumerate(q["option_images"]):
                correct = i == ans_idx
                op = tight(doc.add_paragraph(), 1)
                run(op, f"   ({LABELS[i]}) ", size=11, bold=correct,
                    color=GREEN if correct else None)
                if correct:
                    run(op, "✓ ", size=11, bold=True, color=GREEN)
                op.add_run().add_picture(str(_img_path(rel)), width=Cm(FIG_W_CM - 1.5))
        else:
            for i, opt in enumerate(q["options"]):
                op = tight(doc.add_paragraph(), 1)
                correct = i == ans_idx
                mark = " ✓" if correct else ""
                run(op, f"   ({LABELS[i]}) {opt}{mark}", size=11,
                    bold=correct, color=GREEN if correct else None)

        ansp = tight(doc.add_paragraph(), 1, before=2)
        run(ansp, "उत्तर: ", size=11, bold=True, color=GREEN)
        # diagram-option questions have no text option to name — just the label
        opts = q.get("options") or []
        ans_txt = f"({q['answer'].lower()})"
        if ans_idx < len(opts):
            ans_txt += f" {opts[ans_idx]}"
        run(ansp, ans_txt, size=11, bold=True, color=GREEN)

        if q.get("solution"):
            sp = tight(doc.add_paragraph(), 2)
            run(sp, "हल / व्याख्या: ", size=11, bold=True)
            run(sp, q["solution"], size=11)
        elif q.get("reason"):
            rp = tight(doc.add_paragraph(), 2)
            run(rp, "संकेत: ", size=10, bold=True, color=GREY)
            run(rp, q["reason"], size=10, color=GREY)

        # Source provenance + manual-review flag — TEACHER DOC ONLY (never the
        # branded PPT/paper). Live papers carry "sources": [...] per question;
        # when the two Tier-1 sources don't both confirm, the answer is flagged
        # in RED so Mayank checks it before it reaches the class.
        srcs = [s.lower() for s in (q.get("sources") or [])]
        if official:
            sp = tight(doc.add_paragraph(), 2)
            run(sp, "✔ स्रोत: ", size=9, bold=True, color=GREEN)
            run(sp, "आधिकारिक उत्तर कुंजी (UKSSSC)", size=9, color=GREY)
        elif srcs:
            sp = tight(doc.add_paragraph(), 2)
            shown = " / ".join(srcs)
            run(sp, "✔ स्रोत: ", size=9, bold=True, color=GREEN)
            run(sp, shown, size=9, color=GREY)
        elif q.get("flag"):
            sp = tight(doc.add_paragraph(), 2)
            run(sp, "⚠ जाँच आवश्यक — ", size=10, bold=True, color=RED)
            run(sp, q["flag"], size=10, color=RED)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    n = len(data["questions"])
    with_sol = sum(1 for q in data["questions"] if q.get("solution"))
    print(f"OK: {out_path} ({n} questions, {with_sol} with worked solutions)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    q = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "review" / "spike3-questions.json"
    data = json.loads(q.read_text(encoding="utf-8"))
    default = data.get("solution_filename") or (
        Path(data.get("filename", "Solution.docx")).stem + " - Solution (Teacher).docx")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "review" / default
    build(q, out)
