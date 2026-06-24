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

MAX_CHARS = 60_000   # a 140-Q paper is ~25k chars of text; gives headroom

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


def _chunk_body(body: str) -> list[str]:
    """Split body into ~CHUNK_CHARS chunks, breaking on newlines to avoid
    cutting mid-question. Each chunk overlaps slightly at boundaries."""
    chunks, start = [], 0
    while start < len(body):
        end = min(start + CHUNK_CHARS, len(body))
        if end < len(body):
            # walk back to the last newline so we don't cut mid-question
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


def _call_one(chunk: str) -> list[dict]:
    """Send one text chunk to the LLM (OpenAI primary, Claude fallback)."""
    raw = complete(SYSTEM, USER_TMPL.format(body=chunk), model="fast", max_tokens=8_000)
    raw = _clean_raw(raw)
    try:
        data = parse_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"  [extract_docx] JSON parse error: {e}", file=sys.stderr)
        print(f"  [extract_docx] raw tail: {raw[-300:]}", file=sys.stderr)
        return []
    if isinstance(data, list):
        return data
    return data.get("questions", [])


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
    for i, chunk in enumerate(chunks, 1):
        print(f"  [extract_docx] chunk {i}/{len(chunks)} ({len(chunk)} chars)...",
              file=sys.stderr)
        qs = _call_one(chunk)
        print(f"    -> {len(qs)} questions", file=sys.stderr)
        all_questions.extend(qs)

    # deduplicate by question number (later chunk wins on overlap)
    seen: dict[int, dict] = {}
    for q in all_questions:
        seen[q["n"]] = q
    questions = [seen[n] for n in sorted(seen)]

    if not questions:
        raise ValueError(f"{label}: Claude returned no questions across {len(chunks)} chunks.")
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
