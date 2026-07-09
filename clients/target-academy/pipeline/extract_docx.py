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


def _stem_key(stem: str) -> str:
    """A normalized identity key for a question stem, used to dedup the same
    question extracted by two chunks WITHOUT merging two genuinely different
    questions.

    Collapse all whitespace, drop punctuation/quotes/brackets that OCR wobbles on,
    lowercase the Latin bits. Keep it CONTENT-based (not just a prefix) so two
    different questions that happen to share an opening clause ("निम्नलिखित में
    से...") don't collide. Empty/near-empty stems return "" (treated as anonymous
    by the caller, never merged)."""
    if not isinstance(stem, str):
        return ""
    s = stem.strip()
    if not s:
        return ""
    # remove punctuation the OCR is inconsistent about; keep letters/digits/spaces
    s = re.sub(r"[\s]+", " ", s)
    s = re.sub(r"[।'\"'‘’“”()\[\]{}.,:;?!\-–—/\\]", "", s)
    s = s.lower().strip()
    # a stem shorter than a few chars can't reliably identify a question
    return s if len(s) >= 6 else ""


def _all_options_placeholder(opts) -> bool:
    """True if a question's options are ALL label placeholders (no real text),
    so the question carries no usable answer choices."""
    if not isinstance(opts, list) or len(opts) < 2:
        return False
    return all(_is_placeholder_option(o) for o in opts)


def _recover_or_drop(questions: list[dict], krutidev_input: bool = True) -> list[dict]:
    """Clean up extracted questions and drop unusable ones.

    `krutidev_input` gates the Kruti-Dev-specific steps: they run ONLY for the
    legacy .docx text-layer path (garbled ASCII). On the CLEAN Unicode path
    (Sarvam Vision) they must NOT run — feeding clean text through the Kruti-Dev
    decoder corrupts English words, and _looks_like_krutidev wrongly flags a
    mostly-English stem ("DNS protocol", "OSI model") as gibberish and DROPS a
    real question. Cover-page and placeholder-option drops are input-agnostic and
    always apply."""
    cleaned, dropped, covers, placeholders = [], 0, 0, 0
    for q in questions:
        if krutidev_input:
            # legacy path only: convert any raw Kruti-Dev the model left behind
            if q.get("stem"):
                q["stem"] = _clean_krutidev(q["stem"])
            if isinstance(q.get("options"), list):
                q["options"] = [_clean_krutidev(o) if isinstance(o, str) else o
                                for o in q["options"]]
        # drop the cover page mis-read as a question (both paths)
        if _looks_like_cover(q.get("stem", "")):
            covers += 1
            continue
        # legacy path only: after recovery, still gibberish? drop it. (Never on the
        # clean path — a legit English-heavy stem is not gibberish.)
        if krutidev_input and q.get("stem") and _looks_like_krutidev(q["stem"]):
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

# The extractor input comes from two very different sources, so the prompt is
# parameterised (see _system_for): the Sarvam Vision OCR path hands us CLEAN
# Unicode already, while the legacy .docx text layer hands us Kruti-Dev-encoded
# ASCII. Telling a clean-Unicode input it is "garbled Kruti-Dev" (the old fixed
# prompt) invited the model to rewrite text that was already correct.

# Shared rules for BOTH input kinds.
_SYSTEM_BASE = """You extract multiple-choice questions (MCQs) from an Indian exam
paper and return JSON. You are the ONLY thing deciding where each question begins
and ends — read the text, understand the structure, and return every question.

Return ONLY a JSON array, no prose, no markdown fences:
[{"n":1,"stem":"question text","options":["opt1","opt2","opt3","opt4"]}]

Rules:
- Extract EVERY question in the text, in the order they appear. Do not skip any,
  do not merge two questions, do not split one question into two.
- "n": the question's number as printed (integer). If unnumbered, count 1,2,3…
- "stem": the FULL question text, VERBATIM. Do NOT paraphrase, translate,
  summarise, "correct", or rewrite it. Join a multi-line stem with single spaces.
- "options": the answer choices, VERBATIM, marker/label stripped (2–6 strings).
- "answer": include ONLY if the paper itself prints an answer key for that
  question (lowercase a/b/c/d matching the option order). Otherwise omit it — do
  NOT guess or solve.
- One line per string value (no literal newlines). No markdown. No prose."""

# Appended when the input is CLEAN Unicode (Sarvam Vision OCR).
_SYSTEM_CLEAN = """
The text is clean Unicode from OCR. It may carry light markdown/table markup
(**bold**, #, |, -) — ignore that formatting, keep the actual question/option text
exactly as written."""

# Appended when the input is legacy Kruti-Dev (the .docx text layer).
_SYSTEM_KRUTIDEV = """
The Hindi text uses Kruti Dev 010 — a legacy font where Devanagari is encoded as
garbled ASCII. Convert it to proper Unicode Devanagari. English words stay
English. This transliteration is the ONLY change you make — do not otherwise
reword the question."""


def _system_for(krutidev_input: bool) -> str:
    return _SYSTEM_BASE + (_SYSTEM_KRUTIDEV if krutidev_input else _SYSTEM_CLEAN)


USER_TMPL = """Extract every MCQ from this exam paper text below.
Return ONLY a JSON array. Each string value must be a single line (no \\n).

--- PAPER TEXT START ---
{body}
--- PAPER TEXT END ---"""

# Page separators the OCR/flatteners emit between pages: a form-feed (\f), or the
# explicit page markers Sarvam / markdown converters sometimes insert. Splitting
# on these gives natural per-page units WITHOUT guessing question boundaries.
_PAGE_SEP = re.compile(
    r"\f"                                   # form feed
    r"|^\s*-{3,}\s*$"                        # markdown horizontal rule / page break
    r"|^\s*#+\s*(?:page|पृष्ठ|पेज)\b.*$"     # "# Page 3" style markers
    r"|^\s*\[?(?:page|पृष्ठ|पेज)\s*\d+\]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# How many times the recursive extractor may split a truncated body before it
# gives up and keeps the partial result. pages -> paragraphs -> lines is 3 levels;
# a 4th is headroom, and each level fans out into a few balanced groups.
_MAX_SPLIT_DEPTH = 4


def _split_pages(body: str) -> list[str]:
    """Split OCR text into pages on form-feeds / page markers. If none are present
    (many OCR outputs have no explicit page breaks), returns the whole body as one
    element — the recursion then drops to paragraphs/lines (see _natural_units)."""
    parts = [p.strip() for p in _PAGE_SEP.split(body) if p and p.strip()]
    return parts if len(parts) > 1 else [body.strip()]


def _natural_units(body: str, depth: int) -> list[str]:
    """Break `body` into progressively finer NATURAL units as recursion deepens —
    NEVER at a guessed question boundary:
        depth 0 -> pages     (form-feeds / page markers)
        depth 1 -> paragraphs (blank-line separated)
        depth 2+ -> lines
    Each is a real structural unit of the document, so a question is only ever
    split if the document itself already split it across that unit (rare), and the
    merge step recombines by content. Returns >1 unit only when a finer split
    actually helps."""
    if depth == 0:
        pages = _split_pages(body)
        if len(pages) > 1:
            return pages
        # no page separators -> fall straight to paragraphs
        depth = 1
    if depth == 1:
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        if len(paras) > 1:
            return paras
        depth = 2
    # finest: individual non-empty lines
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return lines


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


# Output-token budget for one LLM extraction call. A JSON question with 4 options
# is ~120-200 tokens; 16k tokens comfortably holds ~90-120 questions, i.e. a whole
# typical paper in ONE call. This is the real (output) limit — and when it is hit,
# the fix is to feed the LLM smaller NATURAL units of the SAME text (pages, then
# paragraphs), never to chunk the input at a code-guessed question boundary.
_EXTRACT_MAX_TOKENS = 16_000


def _looks_truncated(raw: str) -> bool:
    """Did the model's JSON array get cut off by the output-token cap?

    A last-char check ("ends with ]") is NOT enough: when the cap lands right
    after an object's closing '}' (before the next ',' or the final ']'), the
    array IS truncated but its last char is '}', so a naive check reports complete
    and the page-split recovery never fires -> a silent short paper. Instead,
    balance the brackets: strip fences, ignore brackets inside JSON strings, and
    report truncated if the array/object nesting never returns to zero (i.e. a '['
    or '{' was left open). Empty/no-JSON input is treated as truncated so the
    caller escalates rather than shipping nothing."""
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s).strip()
    if not s:
        return True
    start = s.find("[")
    if start == -1:
        start = s.find("{")
    if start == -1:
        return True                       # no JSON array/object at all
    depth, in_str, esc = 0, False, False
    for ch in s[start:]:
        if esc:
            esc = False
            continue
        if in_str:
            if ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
    # depth>0 => an open bracket was never closed (cut off). in_str => cut inside a
    # string. Either means the response did not finish.
    return depth > 0 or in_str


def _call_llm(body: str, system: str, max_tokens: int = _EXTRACT_MAX_TOKENS):
    """One LLM extraction call over `body`. Returns (questions, truncated).

    Never silently returns [] — salvages partial JSON. `truncated` is True when the
    output looks cut off by the token cap, so the caller can split and retry the
    pieces instead of shipping a short paper."""
    raw = complete(system, USER_TMPL.format(body=body), model="fast",
                   max_tokens=max_tokens)
    truncated = _looks_truncated(raw)
    raw = _clean_raw(raw)
    questions = _parse_questions(raw)
    return questions, truncated


def _merge_ordered(all_questions: list[dict],
                   krutidev_input: bool = True) -> list[dict]:
    """Merge question lists (from one call, or several page-splits) into ONE
    ordered, de-duplicated list — preserving document order, deduping on stem
    content (not the LLM's per-piece numbering), and keeping the more-complete
    copy of any duplicate at its first-seen position. Renumbers 1..N at the end.

    (History: the old per-chunk pipeline deduped by q['n'] and sorted by it, which
    both SHUFFLED — each piece renumbers from 1 — and dropped/duplicated questions.
    Ordering by arrival + stem-content dedup fixes both.)"""
    def _completeness(q: dict) -> tuple:
        opts = q.get("options") or []
        return (len(opts) if isinstance(opts, list) else 0, len(str(q.get("stem", ""))))

    order: list[str] = []
    by_key: dict = {}
    anon = 0
    for q in all_questions:
        key = _stem_key(q.get("stem", ""))
        if not key:                # no usable stem -> never merge these together
            key = f"__anon{anon}__"
            anon += 1
        if key not in by_key:
            by_key[key] = q
            order.append(key)
        elif _completeness(q) > _completeness(by_key[key]):
            by_key[key] = q
    questions = [by_key[key] for key in order]

    # Recover Kruti-Dev the model left un-transliterated (legacy path only); drop
    # cover pages / gibberish / placeholder-only questions so the paper never
    # renders garbage. On the clean Unicode path this SKIPS Kruti-Dev processing
    # so it can't corrupt English or drop a legit English-heavy stem.
    questions = _recover_or_drop(questions, krutidev_input=krutidev_input)

    # Renumber 1..N AFTER dropping (a drop before numbering left gaps like
    # n=[1,3,4], which builders print verbatim and a teacher reads as a MISSING
    # question). Numbering last guarantees a clean contiguous 1..N.
    for i, q in enumerate(questions, 1):
        q["n"] = i
    return questions


def extract_from_text(body: str, label: str = "input",
                      krutidev_input: bool = False) -> dict:
    """Turn paper text into {"questions": [...]} by letting the LLM read it.

    Design (per the product owner): Sarvam Vision / the docx text layer already
    make the page selectable; the LLM — not hand-coded regex — decides where each
    question starts and ends. So we send the WHOLE paper in one call and let the
    model return every question in order. We only split when we must:

      1. whole-paper call (primary) — one LLM call over the entire text.
      2. if that output was truncated by the token cap, split by PAGE (a natural
         boundary the OCR already provides via form-feed / page markers) and
         extract each page-group, then merge.
      3. if even the whole-paper call yields nothing (garbled/odd input), fall
         re-extract each smaller unit with the LLM (never a code boundary split).

    `krutidev_input`: True only for the legacy .docx text-layer path (garbled
    Kruti-Dev ASCII); False for clean Unicode (Sarvam Vision) — this picks the
    right system prompt so we never tell clean text it is "garbled"."""
    if not body.strip():
        raise ValueError(f"{label} has no extractable text.")
    if len(body) > MAX_CHARS:
        raise ValueError(f"{label} is {len(body)} chars (> {MAX_CHARS}). "
                         f"Split the paper or raise MAX_CHARS.")

    system = _system_for(krutidev_input)
    questions = _extract_recursive(body, system, depth=0)
    questions = _merge_ordered(questions, krutidev_input=krutidev_input)
    if not questions:
        raise ValueError(f"{label}: extractor returned no questions.")
    print(f"  [extract] {len(questions)} questions total", file=sys.stderr)
    return {"questions": questions}


def _estimate_question_count(body: str) -> int:
    """Cheap deterministic estimate of how many questions the text holds, from
    the paper's OWN printed numbering ("1." ... "100." at line starts, tolerating
    the OCR markdown's pipe/bold/blockquote prefixes). Distinct numbers only, so
    repeats don't inflate it.

    Used ONLY as a completeness guard (see _extract_recursive): the LLM still
    decides every question boundary — this never chunks or parses questions."""
    nums = set()
    for m in re.finditer(r"(?m)^[\s>|*#-]{0,6}(\d{1,3})[.)]\s", body):
        n = int(m.group(1))
        if 1 <= n <= 300:
            nums.add(n)
    return len(nums)


def _extract_recursive(body: str, system: str, depth: int = 0) -> list[dict]:
    """LLM-ONLY extraction (the product doctrine: OCR -> LLM makes the JSON ->
    code only slots it into builders; code NEVER decides question boundaries).

    Send `body` to the LLM. If the output is truncated by the token cap, split the
    body into SMALLER NATURAL UNITS — pages, then paragraphs, then lines — and
    recurse on each. There is no regex boundary logic and no character-chunker:
    when the model can't fit the answer, it gets less INPUT text (whole natural
    units), never text cut at a guessed question edge. The merge step dedups the
    overlap at any truncation point.
    """
    indent = "  " * (depth + 1)
    print(f"{indent}[extract] LLM call ({len(body)} chars, depth {depth})...",
          file=sys.stderr)
    questions, truncated = _call_llm(body, system)
    print(f"{indent}  -> {len(questions)} questions"
          f"{' (TRUNCATED)' if truncated else ''}", file=sys.stderr)

    # SHORTFALL GUARD: a model can stop early and close the JSON cleanly — a
    # well-formed but INCOMPLETE answer that _looks_truncated cannot catch (seen
    # live: a 100-question paper came back as a tidy 56-question array, shipped
    # silently). Compare against the paper's own printed numbering: if we got
    # far fewer questions than the text visibly numbers, treat it exactly like a
    # truncation so the page-split recovery below kicks in.
    if not truncated and questions:
        est = _estimate_question_count(body)
        if est >= 10 and len(questions) < est * 0.9:
            print(f"{indent}  [extract] SHORTFALL: model returned "
                  f"{len(questions)} questions but the text numbers ~{est} — "
                  f"splitting and retrying so none are silently lost",
                  file=sys.stderr)
            truncated = True

    if not truncated:
        return questions

    # Truncated: split the SAME text into a FEW balanced groups of whole natural
    # units and recurse on each. Splitting by unit COUNT (not char size) is what
    # matters here: truncation is driven by how many QUESTIONS the output holds, and
    # a dense paper of many short questions is small in chars but large in output —
    # a char target would never trigger a split. Halving the units per level always
    # reduces the questions-per-call, so we converge. Guard depth so a single
    # indivisible unit can't loop forever.
    units = _natural_units(body, depth)
    if len(units) <= 1 or depth >= _MAX_SPLIT_DEPTH:
        print(f"{indent}  [extract] WARNING: truncated output could not be split "
              f"further (depth {depth}); keeping {len(questions)} partial questions",
              file=sys.stderr)
        return questions

    groups = _balanced_groups(units, n=max(2, min(4, len(units))))
    print(f"{indent}  [extract] truncated -> {len(groups)} group(s) of units",
          file=sys.stderr)
    out: list[dict] = list(questions)   # keep the partial first-pass questions too
    for grp in groups:
        out.extend(_extract_recursive(grp, system, depth + 1))
    return out


def _balanced_groups(units: list[str], n: int) -> list[str]:
    """Split `units` into `n` contiguous, roughly-equal groups (by unit count),
    each joined back into text. Preserves document order; never splits a unit."""
    n = max(1, min(n, len(units)))
    size = -(-len(units) // n)          # ceil division
    groups = ["\n".join(units[i:i + size]) for i in range(0, len(units), size)]
    return [g for g in groups if g.strip()]


def extract(path: Path) -> dict:
    """Read a .docx and return {"questions": [...]} via Claude.

    This is the LEGACY text-layer path: a .docx stores Devanagari as Kruti-Dev
    encoded ASCII, so we flag the input as Kruti-Dev for the prompt. (The clean
    path is Sarvam Vision -> extract_from_text(..., krutidev_input=False).)"""
    return extract_from_text(read_docx_text(path), label=path.name,
                             krutidev_input=True)


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
