"""One command that turns a solved questions JSON into all three deliverables.

This is the orchestrator behind the `/run-pipeline` skill. It is the SINGLE
entry point for the content workflow — it wraps the three production-locked
generators so nobody has to remember three separate commands with absolute
paths. When we productize, the API calls (vision-read a PDF, generate reasons)
slot in AHEAD of this script; the three generators it calls never change.

THE INPUT GATE (load-bearing):
    The pipeline does NOT start until a single valid questions JSON is sitting
    in  review/input/ . No file, more than one file, or a malformed/short file
    -> the run refuses with a clear message. This is the "doesn't start until
    the right input is in the right folder" guarantee.

Outputs (into review/output/, all gitignored — client IP):
    1. <name> (Class).pptx      branded in-class deck, VERBATIM MCQs, NO answers
    2. <name> - Solution.docx   teacher-only solution: answer + reason/हल + the
                                ⚠ manual-review flags (source provenance lives
                                here ONLY — never on the branded artifacts)
    3. <name>.docx              branded practice paper w/ उत्तरमाला answer key

Usage:
    python run_pipeline.py                 # consume the one file in review/input/
    python run_pipeline.py path/to/q.json  # explicit file (skips the folder gate)

JSON shape (per question): { "n", "stem", "options":[...], "answer":"a".."e",
    "reason"?, "solution"?, "sources"?:[...], "flag"? }  — top-level keys
    "filename"/"ppt_filename"/"solution_filename" set the client-facing names.

PAPER FORMAT (top-level "format" key, default "format-1"):
    "format-1"  the branded 2-column practice paper + उत्तरमाला answer key
                (build_paper). The default — what was demoed and locked.
    "format-2"  the per-question 8-row table layout (build_paper_format2),
                every option pre-marked "incorrect". No answer key page (the
                table layout carries answers in its own cells). When format-2
                is selected it REPLACES the format-1 paper; deck + solution +
                answer-key PDF are still produced.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_deck          # noqa: E402
import build_paper         # noqa: E402
import build_paper_format2 # noqa: E402
import build_solution      # noqa: E402
import build_answer_key    # noqa: E402

BASE = Path(__file__).resolve().parents[1]
INPUT_DIR = BASE / "review" / "input"
OUTPUT_DIR = BASE / "review" / "output"

MIN_QUESTIONS = 1
REQUIRED_Q_KEYS = ("n", "stem", "options", "answer")


class GateError(Exception):
    """Raised when the input gate is not satisfied — pipeline must not start."""


def find_input() -> Path:
    """Return the single JSON in review/input/, or refuse with a clear reason."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    jsons = sorted(INPUT_DIR.glob("*.json"))
    if not jsons:
        raise GateError(
            f"No questions JSON found in {INPUT_DIR}\n"
            f"   Drop exactly one solved questions file there, then re-run."
        )
    if len(jsons) > 1:
        names = ", ".join(p.name for p in jsons)
        raise GateError(
            f"{len(jsons)} JSON files in {INPUT_DIR} ({names}).\n"
            f"   The pipeline runs on exactly ONE paper at a time — leave one, "
            f"move the rest out."
        )
    return jsons[0]


def validate(path: Path) -> dict:
    """Parse + structurally check the questions JSON. Refuse on any problem."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GateError(f"{path.name} is not valid JSON: {e}")

    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) < MIN_QUESTIONS:
        raise GateError(
            f"{path.name} has no usable 'questions' array "
            f"(need a list of >= {MIN_QUESTIONS})."
        )

    crop_base = path.resolve().parent  # image paths resolve beside the JSON
    problems = []
    for i, q in enumerate(questions, start=1):
        qid = q.get("n", i)
        # every question needs n, stem, answer
        for k in ("n", "stem", "answer"):
            if k not in q:
                problems.append(f"Q{qid}: missing '{k}'")
        # options come EITHER as text "options" OR diagram "option_images"
        opts = q.get("options")
        opt_imgs = q.get("option_images")
        n_opts = len(opt_imgs) if opt_imgs else (len(opts) if isinstance(opts, list) else 0)
        if not opt_imgs and (not isinstance(opts, list) or len(opts) < 2):
            problems.append(f"Q{qid}: needs >= 2 options (text) or option_images (diagrams)")
        elif "answer" in q:
            # A blank answer is allowed (unmarked / no key). A non-blank answer
            # must be a SINGLE valid option letter. NOTE: the old test used
            # `ans not in "abcdef"[:n_opts]` — a SUBSTRING test, so junk like
            # "ab" passed ("ab" in "abcd" is True) then crashed the builder at
            # "abcdef".index("ab"). Test membership in the letter LIST instead.
            ans = str(q["answer"]).strip().lower()
            if ans and ans not in list("abcdef"[:n_opts]):
                problems.append(
                    f"Q{qid}: answer '{q['answer']}' out of range for {n_opts} options"
                )
        # any referenced crop MUST exist on disk — a missing diagram in class is fatal
        for ref in ([q["image"]] if q.get("image") else []) + (opt_imgs or []):
            rp = Path(ref)
            if not (rp if rp.is_absolute() else crop_base / rp).exists():
                problems.append(f"Q{qid}: image not found -> {ref}")
    if problems:
        raise GateError(
            f"{path.name} has {len(problems)} bad question(s):\n   "
            + "\n   ".join(problems[:10])
            + ("\n   ..." if len(problems) > 10 else "")
        )
    return data


def output_names(data: dict) -> tuple[str, str, str, str]:
    """Client-facing filenames for (deck, solution, paper, answer_key_pdf)."""
    base = data.get("filename", "Practice Paper - Target Academy.docx")
    stem = Path(base).stem
    deck = data.get("ppt_filename") or f"{stem} (Class).pptx"
    sol = data.get("solution_filename") or f"{stem} - Solution (Teacher).docx"
    akey = data.get("answer_key_filename") or f"{stem} - Answer Key.pdf"
    return deck, sol, base, akey


def review_summary(data: dict) -> tuple[int, int, list[str]]:
    """Count questions and surface which ones the teacher must eyeball.

    An answer is FLAGGED only when provenance is genuinely unreliable:
      - explicit per-question "flag" (set by verify_answers.py for conflicts or
        truly unverifiable questions), OR
      - no sources at all AND no worked solution (answer was never checked).
    It is NOT flagged when:
      - the whole paper declares "answer_source": "official_key", OR
      - "sources" has any reliable site(s) — even one exam site is enough, OR
      - it carries a worked "solution" (self-verifying maths/reasoning).
    Rationale: for niche UK-specific questions a single authoritative source
    (e.g. ExamPillar UK section) is the best available evidence — requiring both
    Tier-1 sites caused false flags because Testbook rarely covers UK specifics.
    """
    if data.get("answer_source") == "official_key":
        return len(data["questions"]), 0, []
    flagged = []
    for q in data["questions"]:
        srcs = q.get("sources") or []
        if q.get("flag"):
            flagged.append(str(q["n"]))
        elif not srcs and not q.get("solution"):
            flagged.append(str(q["n"]))
    return len(data["questions"]), len(flagged), flagged


def run(input_path: Path | None = None, font: str | None = None) -> dict:
    """Validate -> generate all three -> return a result dict for the caller.

    `font` ("krutidev" | "unicode") selects the Devanagari rendering for every
    builder. Defaults to the JSON's top-level "font" key, else the shipping
    default ("krutidev"). This is the frontend's per-build font choice.
    """
    src = input_path or find_input()
    data = validate(src)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    font = (font or data.get("font") or "krutidev").lower()

    deck_name, sol_name, paper_name, akey_name = output_names(data)
    deck_out = OUTPUT_DIR / deck_name
    sol_out = OUTPUT_DIR / sol_name
    paper_out = OUTPUT_DIR / paper_name
    akey_out = OUTPUT_DIR / akey_name

    # 1. in-class deck — verbatim MCQs, NO answers shown live
    build_deck.build(src, deck_out, answer_key=False, font=font)
    # 2. teacher solution — answers + reasoning + manual-review flags
    build_solution.build(src, sol_out, font=font)
    # 3. branded practice paper — format-1 (2-col + उत्तरमाला) or format-2 (tables)
    fmt = (data.get("format") or "format-1").lower()
    if fmt == "format-2":
        build_paper_format2.build(src, paper_out, font=font)
    else:
        build_paper.build(src, paper_out, font=font)
    # 3b. also render the paper as a PDF. The .docx is Kruti Dev encoded, so it
    # only reads correctly on a machine with the Kruti Dev font installed; the
    # PDF embeds the font (rendered by LibreOffice server-side, which has it) so
    # the Hindi displays correctly for everyone. Keep the .docx too (editable).
    paper_pdf_out = paper_out.with_suffix(".pdf")
    outputs = [deck_out, sol_out, paper_out, akey_out]
    try:
        build_answer_key._docx_to_pdf(paper_out, paper_pdf_out)
        outputs.append(paper_pdf_out)
    except Exception as e:
        # don't fail the whole job if PDF conversion hiccups — ship the docx.
        print(f"[run_pipeline] paper PDF conversion failed ({type(e).__name__}: {e}); "
              f"delivering .docx only", file=sys.stderr)
    # 4. simple one-page answer-key PDF (owner request)
    build_answer_key.build(src, akey_out, font=font)

    # NOTE: we deliberately do NOT build a merged "<name> - Complete.pdf". For
    # Full Run the frontend delivers the Format B paper PDF alone, because the
    # format-2 table ALREADY contains everything per question (options, the
    # "correct" marking, and the Solution row) — a separate answer key +
    # solution merge was redundant. It also caused a real bug: a "Complete.pdf"
    # (which carries answers) sorted ahead of the plain paper in the output list
    # and got served to students by the paper download matcher. Removed.

    n, n_flag, flagged = review_summary(data)
    return {
        "input": src,
        "outputs": outputs,
        "questions": n,
        "flagged": flagged,
        "n_flagged": n_flag,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    explicit = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    try:
        res = run(explicit)
    except GateError as e:
        print(f"GATE: {e}")
        sys.exit(1)

    print(f"\nOK — pipeline ran on: {res['input'].name}  ({res['questions']} questions)")
    print("Generated:")
    for p in res["outputs"]:
        print(f"   - {p.name}")
    if res["n_flagged"]:
        print(
            f"\n>> {res['n_flagged']} answer(s) flagged for your check "
            f"(Q {', '.join(res['flagged'])}) — see the ⚠ lines in the Solution doc."
        )
    else:
        print("\n>> No answers flagged — every answer is source-confirmed or derived.")
    print(f"\nOutputs in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
