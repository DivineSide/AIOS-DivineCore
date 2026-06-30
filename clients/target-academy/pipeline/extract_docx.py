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

MAX_CHARS = 60_000   # a 140-Q paper is ~25k chars of text; gives headroom

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


def _recover_or_drop(questions: list[dict]) -> list[dict]:
    """Convert-then-drop (Mayank's call): deterministically fix any stem/option
    the model left in raw Kruti-Dev; then drop a question that is STILL gibberish
    so the output never shows garbage. Returns the cleaned list."""
    cleaned, dropped = [], 0
    for q in questions:
        if q.get("stem"):
            q["stem"] = _clean_krutidev(q["stem"])
        if isinstance(q.get("options"), list):
            q["options"] = [_clean_krutidev(o) if isinstance(o, str) else o
                            for o in q["options"]]
        # after recovery, is the stem still gibberish? if so, drop the question.
        if q.get("stem") and _looks_like_krutidev(q["stem"]):
            dropped += 1
            continue
        cleaned.append(q)
    if dropped:
        print(f"  [extract_docx] dropped {dropped} question(s) that stayed "
              f"un-convertible Kruti-Dev gibberish after recovery", file=sys.stderr)
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

    # deduplicate by question number (later chunk wins on overlap). Items missing
    # a usable "n" still count — key them by running order so they aren't dropped.
    seen: dict = {}
    fallback_n = 10_000
    for q in all_questions:
        n = q.get("n")
        if not isinstance(n, int):
            n = fallback_n
            fallback_n += 1
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
