# -*- coding: utf-8 -*-
"""RAG-backed answer marking for extracted questions.

Target Academy's rule (from the team): for each extracted MCQ, look the answer up
in the institute's OWN database (book_chunks via rag_lookup). If we find it WITH
FULL CONFIDENCE, mark the correct option and write a short solution grounded in
that source. If we can't find it confidently, leave the answer BLANK — never
guess. No manual-review flag: a blank simply means "not confidently known".

The confidence gate is two-layered so we don't fake answers:
  1. Retrieval gate: the top book passage must clear RAG_SIM_GATE cosine similarity
     (the question's topic actually exists in the institute's books).
  2. Grounding gate: an LLM, given ONLY those passages, must pick one option AND
     report high confidence AND cite the passage. If it hedges, we leave blank.

Populates on each question dict:
  q["answer"]   = "a"/"b"/... (the correct option letter)  — only when confident
  q["solution"] = short Hindi explanation grounded in the source — only when confident
Leaves both absent/empty otherwise. Never raises: any failure => leave blank.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
RAG = Path(__file__).resolve().parents[1] / "rag"
sys.path.insert(0, str(RAG))

from llm import complete, parse_json  # noqa: E402

# Only attempt marking when the best retrieved passage is at least this similar.
# book_chunks similarities run ~0.2-0.6; 0.42 keeps us to questions whose topic
# the institute's books actually cover well. Tunable via env.
RAG_SIM_GATE = float(os.environ.get("ANSWER_RAG_SIM_GATE", "0.42"))
# Enable/disable the whole feature without a code change.
ANSWER_FROM_RAG = os.environ.get("ANSWER_FROM_RAG", "1") == "1"

_LETTERS = ["a", "b", "c", "d", "e", "f"]

_MARK_SYSTEM = """You are an exam answer-key checker for an Indian coaching institute.
You are given ONE multiple-choice question and PASSAGES from the institute's own
study material. Your ONLY job: decide whether THE PASSAGES THEMSELVES state the
answer. This is a reading-comprehension task, NOT a general-knowledge quiz.

Return ONLY JSON, no prose:
{"answer":"a","confidence":"high|low","solution":"<one-line Hindi explanation quoting what the passage says>"}

HARD RULES:
- Use ONLY the passages. Completely ignore anything you personally know.
- "confidence" = "high" ONLY if a passage EXPLICITLY contains the fact that makes
  one option correct. You must be able to point to the exact sentence.
- If the passages do not contain the answer — even if you personally know it —
  set "confidence":"low" and "answer":"". Do NOT answer from memory.
- The "solution" must QUOTE/paraphrase the supporting passage. If you cannot cite
  a passage sentence, it is "low". Never write a solution that says the passages
  don't mention it — that means "low"."""

_MARK_USER = """प्रश्न (Question): {stem}

विकल्प (Options):
{options_block}

संस्थान की सामग्री से प्रासंगिक अंश (Passages from the institute's material):
{passages_block}

इन अंशों के आधार पर सही विकल्प चुनें। यदि अंश निश्चित रूप से उत्तर नहीं देते, तो confidence "low" रखें।
Return ONLY the JSON object."""


def _rag_lookup_sync(stem, options):
    """Call the async rag_lookup from sync code, own event loop, fail-soft."""
    import asyncio
    from query import rag_lookup
    try:
        return asyncio.run(rag_lookup(stem, options))
    except Exception as e:
        print(f"  [answer-rag] lookup failed ({type(e).__name__}: {e})", file=sys.stderr)
        return []


def _mark_one(q: dict) -> bool:
    """Try to mark one question's answer from RAG. Returns True if marked."""
    stem = q.get("stem") or ""
    options = [o for o in (q.get("options") or []) if isinstance(o, str)]
    if not stem or len(options) < 2:
        return False

    passages = _rag_lookup_sync(stem, options)
    # retrieval gate: need a genuinely relevant passage
    if not passages or passages[0].get("similarity", 0) < RAG_SIM_GATE:
        return False

    options_block = "\n".join(f"{_LETTERS[i]}) {o}" for i, o in enumerate(options))
    passages_block = "\n\n".join(
        f"[{i+1}] {p.get('text','')[:600]}" for i, p in enumerate(passages[:4])
    )
    user = _MARK_USER.format(stem=stem, options_block=options_block,
                             passages_block=passages_block)
    try:
        raw = complete(_MARK_SYSTEM, user, model="fast", max_tokens=400)
        data = parse_json(raw)
    except Exception as e:
        print(f"  [answer-rag] mark failed ({type(e).__name__}: {e})", file=sys.stderr)
        return False

    if not isinstance(data, dict):
        return False
    if str(data.get("confidence", "")).lower() != "high":
        return False  # grounding gate: only accept high-confidence answers
    ans = str(data.get("answer", "")).strip().lower()
    if ans not in _LETTERS[:len(options)]:
        return False

    sol = str(data.get("solution", "")).strip()
    # Belt-and-suspenders: reject "high"-confidence answers whose own solution
    # admits the passage did NOT support it (the model answered from memory).
    _NOT_GROUNDED = ("नहीं है", "उल्लिखित नहीं", "उल्लेख नहीं", "नहीं मिलता",
                     "not mentioned", "not in the passage", "does not")
    if not sol or any(marker in sol for marker in _NOT_GROUNDED):
        return False

    q["answer"] = ans
    q["solution"] = sol
    return True


def mark_answers(data: dict) -> dict:
    """Mark answers for every question in-place, from the institute DB, when
    confident. Leaves the rest blank. Never raises."""
    if not ANSWER_FROM_RAG:
        return data
    questions = data.get("questions", [])
    marked = 0
    for q in questions:
        # don't overwrite an answer the source paper already printed
        if q.get("answer"):
            continue
        try:
            if _mark_one(q):
                marked += 1
        except Exception as e:
            print(f"  [answer-rag] q error ({type(e).__name__}: {e})", file=sys.stderr)
    print(f"  [answer-rag] marked {marked}/{len(questions)} answers from the "
          f"institute database (rest left blank)", file=sys.stderr)
    return data
