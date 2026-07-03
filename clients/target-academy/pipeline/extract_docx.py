# -*- coding: utf-8 -*-
"""Generic question extractor for ANY .docx exam paper.

This replaces the one-off extract_set49.py. Instead of hardcoding one file's
option markers and section patterns, it reads the document's full text and asks
Claude to identify the question structure — so it works on any layout the
client hands us (different option styles, bilingual, match/assertion items).

Output is the universal questions JSON the pipeline already consumes:
    {"questions": [{"n", "stem", "options":[...], "answer"?}, ...]}

Kruti-Dev note: legacy non-Unicode papers store Devanagari as ASCII glyph codes.
We pass the raw text through verbatim and tell Claude not to translate it — the
builders re-apply the Kruti Dev 010 font, so the round trip is lossless. English
words stay English. (This is the lesson from the set 49 build.)

Usage:
    python extract_docx.py <paper.docx>                 # -> prints JSON to stdout
    python extract_docx.py <paper.docx> -o out.json     # -> writes file
    python extract_docx.py <paper.docx> -o review/input/paper.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

from docx import Document

sys.path.insert(0, str(Path(__file__).parent))
from llm import complete, parse_json  # noqa: E402
from krutidev import krutidev_to_unicode  # noqa: E402

# Headroom for BOTH paths: the .docx text layer is ~25k chars for a 140-Q paper,
# but Sarvam Vision OCR output is much larger (it wraps content in HTML table
# markup) — a 100-Q paper came back ~80k chars. Cap high enough not to reject a
# legitimate OCR result (which previously fell back to the garbled text path),
# while still guarding against a runaway input.
MAX_CHARS = 250_000

# Devanagari Unicode block — used to tell converted Hindi from raw Kruti-Dev
# (which is ASCII-range Latin "gibberish" like "LFkku gSaA").
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
# ASCII letters that, in bulk, signal unconverted Kruti-Dev legacy text.
_LATINISH = re.compile(r"[A-Za-z]")


def _devanagari_ratio(s: str) -> float:
    """Fraction of letter-characters that are Devanagari. ~1.0 = clean Hindi,
    near 0 with many Latin letters = raw Kruti-Dev that never got converted."""
    deva = len(_DEVANAGARI.findall(s))
    latin = len(_LATINISH.findall(s))
    total = deva + latin
    return deva / total if total else 1.0


def _looks_like_krutidev(s: str) -> bool:
    """A Hindi-language field that is mostly Latin letters is almost certainly
    raw Kruti-Dev the model failed to transliterate. English-only option text
    (rare) is short, so require some length before flagging."""
    if not s or len(s) < 4:
        return False
    return _devanagari_ratio(s) < 0.4 and len(_LATINISH.findall(s)) >= 4


# A run of Kruti-Dev: Latin letters mixed with the punctuation/digits the legacy
# encoding uses (] [ { } % : ; etc.), long enough to be real text not a stray word.
_KD_RUN = re.compile(r"[A-Za-z][A-Za-z0-9 \]\[{}%:;,.'\"&+/=#-]{3,}")


def _clean_krutidev(s: str) -> str:
    """Deterministically repair Kruti-Dev that the model failed to transliterate.

    The model often converts the FIRST part of a long field and leaves the rest
    as raw Kruti-Dev ("नकशा ,द द{kk esa] dk LFkku..."), so judging the whole
    string misses these. Instead, find each embedded run of Kruti-Dev and convert
    just that run — the same deterministic table the builders use, in reverse.
    No LLM involved.
    """
    if not s:
        return s

    # whole-string case: clearly all Kruti-Dev -> convert the whole thing
    if _looks_like_krutidev(s):
        converted = krutidev_to_unicode(s)
        if _devanagari_ratio(converted) > _devanagari_ratio(s):
            return converted

    # mixed case: convert only the Latin-gibberish runs embedded in the Hindi
    def _sub(m):
        run = m.group(0)
        conv = krutidev_to_unicode(run)
        # only swap in the conversion if it actually became Devanagari
        return conv if _DEVANAGARI.search(conv) else run

    return _KD_RUN.sub(_sub, s)


# The OCR sometimes transcribes the paper's COVER PAGE (logo, "Target Academy",
# the archer image) as if it were a question — "छवि में एक ... लोगो है ... एक
# तीरंदाज का चित्र है". Detect a stem that is describing an image/logo rather than
# asking a question, so we drop it instead of shipping a junk Q1.
_COVER_MARKERS = ("छवि", "लोगो", "तीरंदाज", "चित्र है", "गोलाकार",
                  "logo", "image", "archer", "blank page", "खाली")


def _looks_like_cover(stem: str) -> bool:
    if not stem:
        return False
    s = stem.lower()
    hits = sum(1 for m in _COVER_MARKERS if m.lower() in s)
    # a real question rarely stacks 2+ of these; a logo/cover description does
    return hits >= 2


# Some source papers (esp. drafts) print the options as literal LABEL letters —
# अ/ब/स/द (Hindi a/b/c/d) or a/b/c/d — with no actual answer text. Extracted
# verbatim, they yield options like ['अ','ब','स','द'], which are meaningless in
# the output (the teacher sees "अ / ब / स / द" as the choices, and marking one
# "correct" is nonsense). Detect an option that is JUST a label placeholder.
_LABEL_CHARS = set("अआइईउऊएऐओऔकखगघabcdefABCDEF")


def _is_placeholder_option(opt: str) -> bool:
    """True if the option is just a label letter (अ/ब/स/द, a/b/c...) with no
    real content — i.e. after stripping brackets/dots/spaces it's <=1 letter."""
    if not isinstance(opt, str):
        return False
    core = opt.strip().strip("().[]। :-").strip()
    return len(core) <= 1


def _all_options_placeholder(opts) -> bool:
    """True if a question's options are ALL label placeholders (no real text),
    so the question carries no usable answer choices."""
    if not isinstance(opts, list) or len(opts) < 2:
        return False
    return all(_is_placeholder_option(o) for o in opts)


def _recover_or_drop(questions: list[dict]) -> list[dict]:
    """Convert-then-drop (Mayank's call): deterministically fix any stem/option
    the model left in raw Kruti-Dev; then drop a question that is STILL gibberish
    (or is actually the cover page transcribed as a question) so the output never
    shows garbage. Returns the cleaned list."""
    cleaned, dropped, covers, placeholders = [], 0, 0, 0
    for q in questions:
        if q.get("stem"):
            q["stem"] = _clean_krutidev(q["stem"])
        if isinstance(q.get("options"), list):
            q["options"] = [_clean_krutidev(o) if isinstance(o, str) else o
                            for o in q["options"]]
        # drop the cover page mis-read as a question
        if _looks_like_cover(q.get("stem", "")):
            covers += 1
            continue
        # after recovery, is the stem still gibberish? if so, drop the question.
        if q.get("stem") and _looks_like_krutidev(q["stem"]):
            dropped += 1
            continue
        # drop a question whose options are ALL just label letters (अ/ब/स/द) —
        # the source printed placeholders, not real choices, so it's unusable.
        if _all_options_placeholder(q.get("options")):
            placeholders += 1
            continue
        cleaned.append(q)
    if covers:
        print(f"  [extract_docx] dropped {covers} cover/image-description "
              f"pseudo-question(s)", file=sys.stderr)
    if dropped:
        print(f"  [extract_docx] dropped {dropped} question(s) that stayed "
              f"un-convertible Kruti-Dev gibberish after recovery", file=sys.stderr)
    if placeholders:
        print(f"  [extract_docx] dropped {placeholders} question(s) whose options "
              f"were only label placeholders (अ/ब/स/द), not real choices",
              file=sys.stderr)
    return cleaned

SYSTEM = """You extract MCQs from Indian exam paper text and return JSON.

The Hindi text uses Kruti Dev 010 — a legacy font where Devanagari is encoded as
garbled ASCII. Convert it to proper Unicode Devanagari. English words stay English.

Return ONLY a JSON array, no prose, no markdown fences:
[{"n":1,"stem":"Unicode Hindi stem","options":["opt1","opt2","opt3","opt4"]}]

Rules:
- Convert ALL Kruti Dev garbled text to Unicode Devanagari Hindi.
- "n": question number as integer.
- "stem": full question on one line. Join sub-statements with space.
- "options": 2-6 strings, marker stripped, each on one line.
- "answer": only if paper prints a key (lowercase a/b/c/d). Else omit.
- No newlines inside string values. No markdown. No prose."""

USER_TMPL = """Extract every MCQ from this exam paper section.
Return ONLY a JSON array. Each string value must be a single line (no \\n).

--- PAPER TEXT START ---
{body}
--- PAPER TEXT END ---

[{{"n":1,"stem":"full stem on one line","options":["opt1","opt2","opt3","opt4"]}}]"""

CHUNK_CHARS = 4_000   # ~10-15 questions per chunk; keeps output small for Haiku


def read_docx_text(path: Path) -> str:
    """Flatten a .docx to text, preserving paragraph and table-cell order.

    Run text is concatenated verbatim (legacy-font bytes included). Paragraphs
    are newline-separated; table cells are tab-separated so Claude can still see
    row structure for match/grid questions.
    """
    doc = Document(str(path))
    lines: list[str] = []

    def para_text(p) -> str:
        return "".join(r.text for r in p.runs)

    # python-docx exposes body paragraphs and tables separately; walking the
    # body element keeps them in document order.
    from docx.oxml.ns import qn
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph
            t = para_text(Paragraph(child, doc)).strip()
            if t:
                lines.append(t)
        elif child.tag == qn("w:tbl"):
            from docx.table import Table
            tbl = Table(child, doc)
            for row in tbl.rows:
                cells = ["".join(r.text for p in c.paragraphs for r in p.runs).strip()
                         for c in row.cells]
                if any(cells):
                    lines.append("\t".join(cells))
    return "\n".join(lines)


# A line that STARTS a new question. Two shapes cover both input paths:
#   1. A numbered line: "1.", "2)", "12 -", "१." (digital-PDF / plain-text papers).
#   2. A "Question" field label (the docx TABLE flattener emits each question as
#      "Question\t<stem>", and Sarvam OCR of these table papers also transcribes a
#      literal "Question" line). This is the anchor for Target Academy's format.
# Matched at the start of a line only (re.MULTILINE), so a "1." inside a stem or
# an inline "question" word never counts as a boundary.
# The numbered form requires a SPACE/TAB (or line end) right after the delimiter,
# so a question line "1. पहला प्रश्न" matches but a dotted-decimal inside a stem
# ("142.250.190.46", where a digit follows the dot) does NOT — that false boundary
# would otherwise split a question mid-stem.
_Q_BOUNDARY = re.compile(
    r"^(?:\s*(?:[0-9०-९]{1,3}[.)\-।]|Q\.?\s*[0-9]{1,3}[.)]?)(?=[ \t]|$)|"
    r"\s*Question\b)",
    re.MULTILINE,
)


def _question_starts(body: str) -> list[int]:
    """Character offsets where a new question begins (see _Q_BOUNDARY)."""
    return [m.start() for m in _Q_BOUNDARY.finditer(body)]


def _chunk_body(body: str) -> list[str]:
    """Split body into ~CHUNK_CHARS chunks, cutting ONLY at a question boundary so
    a question is never split across two chunks. NO overlap.

    Why structure-aware: the old version cut at the last NEWLINE before the cap,
    which almost always lands mid-question — so the question straddling the
    boundary lost its stem opening (rendered as a fragment) or its trailing
    options (rendered with 3 choices), and sometimes vanished entirely. On SET-04
    that produced a fragment Q1, a 3-option Q, and ~17 missing questions.

    Fix: find every question-start offset (_question_starts) and pack whole
    questions into each chunk greedily up to CHUNK_CHARS, breaking the chunk right
    BEFORE the boundary that would overflow it. A single question larger than
    CHUNK_CHARS (rare) still gets its own chunk — we never drop or truncate it, we
    just let that one chunk run long. If the text has no detectable boundaries at
    all (unknown format), fall back to the old newline split so we still make
    progress. Overlap was tried before and made things WORSE (empty later chunks +
    duplicates); this recovers the boundary questions WITHOUT re-feeding any text.
    """
    starts = _question_starts(body)
    # No structure detected -> fall back to the newline split (never worse than before).
    if len(starts) < 2:
        return _chunk_body_by_newline(body)

    # Treat the region before the first boundary (cover/header) as a leading block,
    # and make the boundary list span the whole document.
    bounds = starts + [len(body)]
    if bounds[0] != 0:
        bounds = [0] + bounds

    chunks: list[str] = []
    chunk_start = bounds[0]
    for i in range(1, len(bounds)):
        b = bounds[i]
        # If extending the current chunk to this boundary would exceed the cap AND
        # the current chunk already holds at least one question, close it here.
        if b - chunk_start > CHUNK_CHARS and bounds[i - 1] > chunk_start:
            chunks.append(body[chunk_start:bounds[i - 1]].strip())
            chunk_start = bounds[i - 1]
    # Trailing remainder (the last chunk).
    if chunk_start < len(body):
        chunks.append(body[chunk_start:].strip())
    return [c for c in chunks if c]


def _chunk_body_by_newline(body: str) -> list[str]:
    """Fallback splitter: break on the last newline before the cap. Used only when
    no question boundaries are detected (see _chunk_body)."""
    chunks, start = [], 0
    while start < len(body):
        end = min(start + CHUNK_CHARS, len(body))
        if end < len(body):
            nl = body.rfind("\n", start, end)
            if nl > start:
                end = nl
        chunks.append(body[start:end].strip())
        start = end
    return [c for c in chunks if c]


def _clean_raw(raw: str) -> str:
    """Strip markdown fences and fix literal newlines inside JSON strings.

    Two problems Claude introduces:
    1. Wraps output in ```json ... ``` fences (with or without trailing newline)
    2. Puts literal newline characters inside JSON string values

    We fix both before handing to json.loads.
    """
    # Strip fences — handles ```json, ```, and trailing ``` anywhere
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```\s*$", "", raw)

    # Replace literal newlines/carriage returns inside string values with space.
    # State machine: track whether we're inside a JSON string.
    result = []
    in_string = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and in_string:
            # escaped character — pass both chars through unchanged
            result.append(ch)
            i += 1
            if i < len(raw):
                result.append(raw[i])
            i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch in ("\n", "\r"):
            result.append(" ")
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def _salvage_questions(raw: str) -> list[dict]:
    """Recover whatever valid question objects we can from a malformed response.

    The model occasionally returns JSON that won't parse as a whole — a trailing
    comma, an unescaped backslash/quote from legacy Kruti-Dev text, a missing
    delimiter, or extra data after the array. Rather than throw away the ENTIRE
    chunk (which silently loses ~15 questions), scan the text for individual
    {"n":..,"stem":..,"options":[..]} objects and json.loads each one on its own.
    One bad object loses one question, not the whole chunk.
    """
    salvaged: list[dict] = []
    # find each top-level object that starts with an "n" key (a question item)
    for m in re.finditer(r'\{\s*"n"\s*:', raw):
        start = m.start()
        depth, in_str, esc = 0, False, False
        for i in range(start, len(raw)):
            ch = raw[i]
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    frag = raw[start:i + 1]
                    try:
                        obj = json.loads(frag)
                        if isinstance(obj, dict) and "n" in obj and obj.get("options"):
                            salvaged.append(obj)
                    except (ValueError, json.JSONDecodeError):
                        pass  # this one object is unrecoverable; skip just it
                    break
    return salvaged


def _parse_questions(raw: str) -> list[dict]:
    """Parse a model response into a list of question dicts, tolerantly.

    First try the clean whole-document parse; if that fails, salvage individual
    objects so a single malformed item never costs us the whole chunk."""
    try:
        data = parse_json(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("questions", [])
    except (ValueError, json.JSONDecodeError):
        pass
    return _salvage_questions(raw)


def _call_one(chunk: str, attempt: int = 1) -> list[dict]:
    """Send one text chunk to the LLM (OpenAI primary, Claude fallback).

    On a chunk that yields zero parseable questions, retry once — the model is
    non-deterministic and a second pass usually returns clean JSON. Never
    silently drops a chunk: salvages partial JSON and logs the outcome.
    """
    raw = complete(SYSTEM, USER_TMPL.format(body=chunk), model="fast", max_tokens=8_000)
    raw = _clean_raw(raw)
    questions = _parse_questions(raw)

    if not questions and attempt < 2:
        print(f"  [extract_docx] chunk parsed to 0 questions; retrying (attempt {attempt + 1})",
              file=sys.stderr)
        return _call_one(chunk, attempt + 1)

    if not questions:
        # genuinely couldn't recover anything from this chunk after a retry —
        # make the loss LOUD instead of silently returning [] (the old bug).
        print(f"  [extract_docx] WARNING: lost a chunk entirely after retry. "
              f"raw tail: {raw[-300:]}", file=sys.stderr)
    return questions


def extract_from_text(body: str, label: str = "input") -> dict:
    """Send paper text to Claude in chunks -> {"questions": [...]}.

    Shared by the .docx and digital-PDF paths. Chunks at ~8k chars so the
    output per call always fits within the model's output window.
    """
    if not body.strip():
        raise ValueError(f"{label} has no extractable text.")
    if len(body) > MAX_CHARS:
        raise ValueError(f"{label} is {len(body)} chars (> {MAX_CHARS}). "
                         f"Split the paper or raise MAX_CHARS.")

    chunks = _chunk_body(body)
    all_questions: list[dict] = []
    lost_chunks = 0
    for i, chunk in enumerate(chunks, 1):
        print(f"  [extract_docx] chunk {i}/{len(chunks)} ({len(chunk)} chars)...",
              file=sys.stderr)
        qs = _call_one(chunk)
        print(f"    -> {len(qs)} questions", file=sys.stderr)
        if not qs:
            lost_chunks += 1
        all_questions.extend(qs)

    # deduplicate by question number. With chunk OVERLAP a boundary question can
    # appear twice — once TRUNCATED (the chunk that cut it) and once COMPLETE (the
    # chunk that re-included it). Keep the MORE COMPLETE copy: prefer the one with
    # more options, then the longer stem — NOT simply "later wins" (which could
    # keep the truncated copy). Items missing a usable "n" key by running order.
    def _completeness(q: dict) -> tuple:
        opts = q.get("options") or []
        return (len(opts) if isinstance(opts, list) else 0, len(str(q.get("stem", ""))))

    seen: dict = {}
    fallback_n = 10_000
    for q in all_questions:
        n = q.get("n")
        if not isinstance(n, int):
            n = fallback_n
            fallback_n += 1
        prev = seen.get(n)
        if prev is None or _completeness(q) >= _completeness(prev):
            seen[n] = q
    questions = [seen[n] for n in sorted(seen)]

    # Recover any text the model left in raw Kruti-Dev (it tends to give up on
    # the transliteration late in a long response); drop anything still gibberish
    # so the paper never renders garbage.
    questions = _recover_or_drop(questions)

    if not questions:
        raise ValueError(f"{label}: extractor returned no questions across {len(chunks)} chunks.")
    if lost_chunks:
        # surface partial loss rather than quietly shipping a short paper
        print(f"  [extract_docx] NOTE: {lost_chunks}/{len(chunks)} chunk(s) yielded "
              f"nothing even after retry; extracted {len(questions)} questions total.",
              file=sys.stderr)
    return {"questions": questions}


def extract(path: Path) -> dict:
    """Read a .docx and return {"questions": [...]} via Claude."""
    return extract_from_text(read_docx_text(path), label=path.name)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Extract MCQs from any .docx paper.")
    ap.add_argument("docx", type=Path, help="path to the .docx exam paper")
    ap.add_argument("-o", "--out", type=Path, help="write JSON here (else stdout)")
    args = ap.parse_args()

    data = extract(args.docx)
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
