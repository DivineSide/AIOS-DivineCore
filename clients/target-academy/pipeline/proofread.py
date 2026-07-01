# -*- coding: utf-8 -*-
"""Careful OCR proofread pass for extracted questions.

Sarvam Vision OCR is ~98% right but occasionally mis-reads a Hindi character
(e.g. a matra or a similar-looking akshar). Mayank asked to clean these up.

The DANGER: a naive spell-corrector will "correct" a CORRECT rare exam term
(place names, historical figures like "माधो सिंह भंडारी", scheme names) into a
wrong common word — silently corrupting answers. So this pass is deliberately
conservative: an LLM is told to fix ONLY obvious OCR slips and to NEVER change
proper nouns, numbers, dates, technical terms, or the meaning. If it's unsure,
it must return the text unchanged.

Batched to keep it cheap. Fails soft: on any error a question keeps its original
text (we never drop or blank a question because proofreading hiccuped).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import complete, parse_json  # noqa: E402

PROOFREAD = os.environ.get("PROOFREAD_OCR", "1") == "1"
_BATCH = int(os.environ.get("PROOFREAD_BATCH", "8"))

_SYSTEM = """You proofread Hindi MCQ text produced by OCR. Fix ONLY obvious OCR
mis-reads (a wrong matra, a swapped similar character, a broken word). You must:
- NEVER change proper nouns (names of people, places, schemes, organisations).
- NEVER change numbers, dates, years, or technical/English terms.
- NEVER change the meaning of a question or option.
- If you are not sure a word is an OCR error, LEAVE IT EXACTLY AS IS.

You are given a JSON array of items {id, stem, options}. Return ONLY a JSON array
of the SAME items with the same ids and same structure, text lightly corrected.
Return every item. No prose, no markdown."""

_USER = """Proofread these OCR'd Hindi MCQs. Return the same JSON array, same ids,
same number of options each, only obvious OCR typos fixed:

{payload}"""


def _proof_batch(batch: list[dict]) -> dict:
    """Return {id: {stem, options}} corrections for a batch, or {} on failure."""
    payload = json.dumps(
        [{"id": b["id"], "stem": b["stem"], "options": b["options"]} for b in batch],
        ensure_ascii=False,
    )
    try:
        raw = complete(_SYSTEM, _USER.format(payload=payload), model="fast",
                       max_tokens=4000)
        data = parse_json(raw)
    except Exception as e:
        print(f"  [proofread] batch failed ({type(e).__name__}: {e}); keeping original",
              file=sys.stderr)
        return {}
    out = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "id" in item:
                out[item["id"]] = item
    return out


def proofread(data: dict) -> dict:
    """Lightly OCR-proofread every question in-place. Never raises; on any issue
    a question keeps its original text."""
    if not PROOFREAD:
        return data
    questions = data.get("questions", [])
    # index by a stable id so a batch reply maps back safely
    indexed = []
    for i, q in enumerate(questions):
        if q.get("stem"):
            indexed.append({"id": i, "stem": q["stem"],
                            "options": [o for o in (q.get("options") or []) if isinstance(o, str)]})

    fixed = 0
    for start in range(0, len(indexed), _BATCH):
        batch = indexed[start:start + _BATCH]
        corr = _proof_batch(batch)
        for item in batch:
            c = corr.get(item["id"])
            if not isinstance(c, dict):
                continue
            q = questions[item["id"]]
            new_stem = str(c.get("stem", "")).strip()
            new_opts = c.get("options")
            # only apply if structure is preserved (same option count)
            if new_stem:
                q["stem"] = new_stem
            if (isinstance(new_opts, list)
                    and len(new_opts) == len(item["options"])
                    and all(isinstance(o, str) for o in new_opts)):
                q["options"] = new_opts
            fixed += 1
    print(f"  [proofread] OCR-proofread {fixed}/{len(questions)} questions",
          file=sys.stderr)
    return data
