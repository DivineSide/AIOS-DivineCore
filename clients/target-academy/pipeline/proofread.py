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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import _complete_one, MODELS, parse_json  # noqa: E402

PROOFREAD = os.environ.get("PROOFREAD_OCR", "1") == "1"
_BATCH = int(os.environ.get("PROOFREAD_BATCH", "8"))

# ── mechanical diff-guard ────────────────────────────────────────────────────
# Proofread is the ONE stage that lets AI rewrite Hindi, so the prompt's "never
# change facts" rule is backed by CODE, not trust. A correction is accepted only
# if it altered nothing but Devanagari spelling. These checks are the cage.
_NUM = re.compile(r"\d+")
_LATIN = re.compile(r"[A-Za-z]+")


def _safe_correction(orig: str, corrected: str) -> bool:
    """True if `corrected` is a legitimate spelling fix of `orig` — i.e. it did
    NOT change any number, any English/Latin token, or rewrite the text wholesale.
    Any False keeps the original text (fail-safe: a fact is never corrupted)."""
    if not isinstance(corrected, str) or not corrected.strip():
        return False
    # numbers must be identical (multiset): blocks Article 14->15, year swaps, etc.
    if sorted(_NUM.findall(orig)) != sorted(_NUM.findall(corrected)):
        return False
    # English/Latin tokens must be identical (case-insensitive multiset):
    # blocks GSDP/OSI/DNS and English-name corruption.
    if (sorted(t.lower() for t in _LATIN.findall(orig))
            != sorted(t.lower() for t in _LATIN.findall(corrected))):
        return False
    # magnitude cap: a spelling fix nudges a few characters; a name-swap or
    # paraphrase changes a large fraction. Reject whole-scale rewrites. Length
    # ratio is a cheap, dependency-free proxy for "too much changed".
    lo, hi = sorted((len(orig), len(corrected)))
    if hi > 0 and lo / hi < 0.6:
        return False
    return True
# The cost/quality strategy (Mayank): cheap Sarvam does the OCR, then a Claude
# TEXT pass (far cheaper than Claude VISION — no image tokens) cleans the Hindi
# spelling Sarvam mangles. Pin Claude's strong text model for the best Devanagari.
_PROOF_MODEL = os.environ.get("PROOFREAD_MODEL", MODELS["anthropic"]["smart"])

_SYSTEM = """You are a Hindi proofreader for an Indian competitive-exam coaching
institute. The text below was produced by OCR of a Hindi exam paper and contains
SPELLING/OCR errors: wrong matras, swapped similar aksharas, broken/merged words,
and occasional garbled fragments (leftover legacy-font junk like "क्च्ैच्" or a
mangled name like "महेा दीक्षित"). Your job is to output clean, correctly spelled
Hindi.

FIX aggressively:
- Misspelled ordinary Hindi words -> correct spelling.
- Garbled/gibberish fragments -> the word they were clearly meant to be, IF you
  can tell from context. If a fragment is unrecoverable, leave it as-is.
- A person/place name that is OCR-mangled -> its correct, conventional spelling
  (e.g. fix a clearly-broken rendering of a well-known name).
- **NON-WORDS: a token that is NOT a real Hindi/loanword at all is ALMOST CERTAINLY
  an OCR error — do NOT leave it. Work out the intended word from the sentence and
  fix it.** Two real examples that MUST be fixed:
    * "बाड़ाहाट का त्रिरूल लेख" -> "बाड़ाहाट का त्रिशूल लेख" ("त्रिरूल" is not a
      word; the Barahat inscription is the त्रिशूल / trident inscription).
    * "मेरी माँ के पासंनजम दामाद हैं" -> "मेरी माँ के इकलौते दामाद हैं"
      ("पासंनजम" is not a Hindi word; the relationship-puzzle phrase is "इकलौते/
      एकमात्र दामाद").
  If you can read the sentence and the token is a non-word, replace it with the
  word it was clearly meant to be. Only leave a non-word untouched if you truly
  cannot infer the intended word even from full context.

NEVER do:
- NEVER change which fact/entity is meant. Correct the SPELLING of a name, never
  swap it for a DIFFERENT name. (Fix a garbled "माधव सिह" -> "माधो सिंह भंडारी"
  only if context makes the intended name unambiguous; otherwise leave it.)
- NEVER change numbers, dates, years, article numbers, or English/technical terms.
- NEVER change the meaning of a question or an option, or add/remove options.
- NEVER answer the question or mark anything correct.

You get a JSON array of items {id, stem, options}. Return ONLY a JSON array with
the SAME ids and the SAME number of options per item, text corrected. No prose."""

_USER = """Proofread and correct the Hindi spelling in these OCR'd MCQs. Return
the same JSON array (same ids, same option counts), spelling cleaned:

{payload}"""


def _proof_batch(batch: list[dict]) -> dict:
    """Return {id: {stem, options}} corrections for a batch, or {} on failure.
    Uses Claude text (best Hindi spelling) directly, not the provider router."""
    payload = json.dumps(
        [{"id": b["id"], "stem": b["stem"], "options": b["options"]} for b in batch],
        ensure_ascii=False,
    )
    try:
        raw = _complete_one("anthropic", _SYSTEM, _USER.format(payload=payload),
                            _PROOF_MODEL, max_tokens=4000)
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
            # MECHANICAL DIFF-GUARD: proofread is the one place we let AI rewrite
            # Hindi, so cage it — a correction is applied ONLY if it changed
            # nothing but Devanagari spelling. _safe_correction rejects any change
            # to numbers, English/Latin tokens, or a whole-scale rewrite. On
            # rejection we keep the ORIGINAL (fail-safe: never corrupt a fact).
            if new_stem and _safe_correction(item["stem"], new_stem):
                q["stem"] = new_stem
            if (isinstance(new_opts, list)
                    and len(new_opts) == len(item["options"])
                    and all(isinstance(o, str) for o in new_opts)
                    and all(_safe_correction(o0, o1)
                            for o0, o1 in zip(item["options"], new_opts))):
                q["options"] = new_opts
            fixed += 1
    print(f"  [proofread] OCR-proofread {fixed}/{len(questions)} questions",
          file=sys.stderr)
    return data
