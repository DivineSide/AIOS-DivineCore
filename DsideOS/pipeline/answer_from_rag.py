# -*- coding: utf-8 -*-
"""RAG-backed answer marking for extracted questions.

Target Academy's rule (from the team): for each extracted MCQ, look the answer up
in the institute's OWN database (book_passages via rag_lookup). If we find it WITH
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
# book_passages similarities run ~0.2-0.6 (same embedding model the chunks used);
# 0.42 keeps us to questions whose topic the institute's books actually cover
# well. Tunable via env if the passage-level distribution proves different.
RAG_SIM_GATE = float(os.environ.get("ANSWER_RAG_SIM_GATE", "0.42"))
# Enable/disable the whole feature without a code change.
ANSWER_FROM_RAG = os.environ.get("ANSWER_FROM_RAG", "1") == "1"

_LETTERS = ["a", "b", "c", "d", "e", "f"]

_MARK_SYSTEM = """You are an exam answer-key checker for an Indian coaching institute.
You are given ONE multiple-choice question and PASSAGES from the institute's own
study material. Your ONLY job: decide whether THE PASSAGES THEMSELVES state the
answer. This is a reading-comprehension task, NOT a general-knowledge quiz.

Return ONLY JSON, no prose:
{"answer":"a","confidence":"high|low","solution":"<2-3 line Hindi explanation of WHY this option is correct>"}

HARD RULES:
- Use ONLY the passages. Completely ignore anything you personally know.
- "confidence" = "high" ONLY if a passage EXPLICITLY contains the fact that makes
  one option correct. You must be able to point to the exact sentence.
- If the passages do not contain the answer — even if you personally know it —
  set "confidence":"low" and "answer":"". Do NOT answer from memory.

SOLUTION QUALITY (this is critical):
- The "solution" must EXPLAIN WHY the correct option is right — the concept, the
  reason, or the fact from the passage that makes it correct. Write it like a
  teacher explaining to a student.
- NEVER write a circular restatement. FORBIDDEN examples (these are NOT solutions):
    * "X इस प्रश्न में बताया गया है।"  ("X is stated in the question.")
    * "सही उत्तर X है क्योंकि यह सही है।"  ("The answer is X because it is correct.")
    * simply repeating the correct option's text back.
  If the only thing you can write is a restatement of the option, then you do NOT
  actually have a grounded explanation — set "confidence":"low" and "answer":"".
- A good solution names the underlying reason. E.g. for "सूचना प्रणाली में संचार
  की प्रासंगिकता": explain that a communication system's purpose is the EXCHANGE of
  important information between parties — that concept is why that option is correct,
  not merely that the option appears."""

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


# Phrases that mark a circular non-explanation ("X is stated in the question /
# book / passage" — i.e. it just points AT the answer instead of explaining it).
_CIRCULAR_MARKERS = (
    "इस प्रश्न में बताया गया", "प्रश्न में बताया गया", "में बताया गया है",
    "सही उत्तर है", "सही विकल्प है", "उपरोक्त में सही",
    "पुस्तक में", "किताब में", "अंश में बताया", "पाठ में बताया",
    "stated in the question", "mentioned in the book", "is the correct",
    "as stated", "given in the passage",
)


def _is_circular_solution(sol: str, correct_opt: str) -> bool:
    """True if `sol` is a circular restatement rather than a real explanation:
    it either uses a 'stated in the question/book' phrase, or is essentially just
    the correct option's own text with little added reasoning."""
    if not sol:
        return True
    s = sol.strip()
    low = s.lower()
    if any(m.lower() in low for m in _CIRCULAR_MARKERS):
        return True
    # If the solution is basically the correct option echoed back (option text is
    # >=70% of the solution and the solution adds almost nothing), it's circular.
    opt = (correct_opt or "").strip()
    if opt and opt in s:
        remainder = s.replace(opt, "").strip(" ।.\"'-—:")
        if len(remainder) < 12:  # option text + a few filler chars = no real why
            return True
    return False


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

    # Reject a CIRCULAR / restatement "solution" — one that just says "X is
    # stated in the question" or echoes the correct option's text back without
    # explaining WHY. That's not a solution; ship the answer but NO solution
    # rather than a fake one. (Mayank flagged: "This is just you saying it is
    # mentioned in the book.")
    correct_idx = _LETTERS.index(ans)
    correct_opt = options[correct_idx] if correct_idx < len(options) else ""
    if _is_circular_solution(sol, correct_opt):
        sol = ""

    q["answer"] = ans
    if sol:
        q["solution"] = sol
    # Provenance: record WHICH institute book(s) grounded this answer so the
    # teacher solution doc shows a source line — a RAG-marked answer must be
    # visibly distinguishable from one the source paper printed. Use the BOOK
    # NAME only (build_solution renders sources via add_latin, which is for
    # Latin filenames; the Hindi `topic` would render wrong there). Dedupe,
    # keep the top few similarity-ordered passages.
    srcs = []
    for p in passages[:4]:
        book = str(p.get("book") or p.get("source_file") or "").strip()
        if book and book not in srcs:
            srcs.append(book)
    if srcs:
        q["sources"] = srcs
    return True


# Mark questions concurrently. Each question is independent network-bound work
# (1 embedding + 1 DB search + 1 LLM call), so a thread pool overlaps the waits
# and turns ~N*Xs of sequential latency into ~(N/workers)*Xs. On a 75-question
# paper the sequential loop took ~4 min and blew past the frontend timeout; this
# collapses it. Tunable/disable-able via env (set workers=1 to serialize).
def _mark_workers() -> int:
    """Worker count for the marking pool. Robust to a bad env value (non-int ->
    default) and CAPPED at 16 so a huge value can't open 100+ simultaneous DB
    connections + LLM calls (each thread holds its own psycopg2 connection)."""
    try:
        n = int(os.environ.get("ANSWER_RAG_WORKERS", "8"))
    except (TypeError, ValueError):
        n = 8
    return max(1, min(n, 16))


_MARK_WORKERS = _mark_workers()


def _mark_one_safe(q: dict) -> bool:
    """_mark_one wrapped so a single question's failure never sinks the pool."""
    try:
        return _mark_one(q)
    except Exception as e:
        print(f"  [answer-rag] q error ({type(e).__name__}: {e})", file=sys.stderr)
        return False


def mark_answers(data: dict) -> dict:
    """Mark answers for every question in-place, from the institute DB, when
    confident. Leaves the rest blank. Never raises. Questions are marked
    concurrently (thread pool) — each mutates its OWN dict, so this is safe."""
    if not ANSWER_FROM_RAG:
        return data
    questions = data.get("questions", [])
    # only mark questions the source paper didn't already answer
    todo = [q for q in questions if not q.get("answer")]
    marked = 0
    if todo:
        from concurrent.futures import ThreadPoolExecutor
        workers = min(_MARK_WORKERS, len(todo))
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                marked = sum(1 for ok in pool.map(_mark_one_safe, todo) if ok)
        except Exception as e:
            # if the pool itself fails, fall back to a plain sequential pass so
            # we never lose marking entirely.
            print(f"  [answer-rag] pool failed ({type(e).__name__}: {e}); "
                  f"marking sequentially", file=sys.stderr)
            marked = sum(1 for q in todo if _mark_one_safe(q))
    print(f"  [answer-rag] marked {marked}/{len(questions)} answers from the "
          f"institute database (rest left blank)", file=sys.stderr)
    return data
