# -*- coding: utf-8 -*-
"""ground — the grounding gate: no generated fact ships unsupported.

The old pipeline's worst failure class was confabulation (a question claiming
उत्तराखंड was formed on the पुंछी आयोग's recommendation — a fact from nowhere).
This gate closes it: for every assembled question, a cheap Haiku call is shown
ONLY the source passages that were in the generation context plus the question
and its claimed answer, and must decide from the passages alone whether they
support it. Contract mirrors answer_from_rag.py's battle-tested marking gate
(reading-comprehension framing, no-outside-knowledge hard rule, must-quote).

Unsupported/hedged -> reject with a reason the retry loop feeds back. The gate
is only as honest as the context — which is why it comes AFTER the corpus
cleanup: verifying against corrupt text would have DEFENDED wrong years.
"""
from __future__ import annotations

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

GROUND_MODEL = os.environ.get("GROUND_MODEL", "claude-haiku-4-5-20251001")
GROUND = os.environ.get("GEN_GROUNDING", "1") == "1"

_SYSTEM = """You are a fact-checker for an exam-question generator. You get SOURCE
PASSAGES (the only material the question was allowed to use), one QUESTION, and
its CLAIMED ANSWER. Decide from the passages ALONE whether they support the
claimed answer.

Return ONLY JSON: {"supported": true|false, "quote": "<the source sentence that
proves it, verbatim, or empty>"}

HARD RULES:
- Use ONLY the passages. Ignore everything you personally know.
- "supported": true ONLY if a passage explicitly contains the fact that makes
  the claimed answer correct — you must be able to quote the sentence.
- For match/order questions: EVERY claimed pairing / the full claimed sequence
  must be supported, not just one element.
- If the passages don't settle it — even if you privately know the answer —
  return {"supported": false, "quote": ""}."""

_USER = """SOURCE PASSAGES:
{passages}

QUESTION:
{question}

CLAIMED ANSWER: ({answer}) {answer_text}
{claim_line}
Do the passages support this? JSON only."""

_client: anthropic.Anthropic | None = None


def _anthropic() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(timeout=60, max_retries=3)
    return _client


def _question_text(q: dict) -> str:
    parts = [q.get("stem", "")]
    parts += [str(s) for s in (q.get("statements") or [])]
    for row in (q.get("match") or []):
        parts.append("   ".join(map(str, row)))
    if q.get("lead_in"):
        parts.append(q["lead_in"])
    for i, o in enumerate(q.get("options") or []):
        parts.append(f"({chr(97 + i)}) {o}")
    return "\n".join(p for p in parts if p)


def check(q: dict, passages: list[dict]) -> tuple[bool, str]:
    """Return (supported, reason_if_not). Fail-open is NOT allowed here — an
    API error counts as unsupported (better to drop a slot than ship a guess);
    the gate can be disabled wholesale via GEN_GROUNDING=0."""
    if not GROUND:
        return True, ""
    if not passages:
        return False, "no source passages were available to ground this question"

    ptxt = "\n\n".join(f"[{i + 1}] {p.get('text', '')[:900]}"
                       for i, p in enumerate(passages[:4]))
    ans = str(q.get("answer", "")).lower()
    idx = "abcd".find(ans)
    opts = q.get("options") or []
    answer_text = opts[idx] if 0 <= idx < len(opts) else ""
    claim_line = f"CLAIMED FACT: {q['_claim']}\n" if q.get("_claim") else ""

    try:
        msg = _anthropic().messages.create(
            model=GROUND_MODEL,
            max_tokens=300,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _USER.format(
                passages=ptxt, question=_question_text(q),
                answer=ans, answer_text=answer_text, claim_line=claim_line)}],
        )
        raw = msg.content[0].text.strip() if msg.content else ""
        raw = raw.strip("`").removeprefix("json").strip()
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception as e:
        logger.warning("ground: check failed (%s: %s) — treating as unsupported",
                       type(e).__name__, e)
        return False, "grounding check errored — regenerate from clearly stated facts"

    if data.get("supported") is True and str(data.get("quote", "")).strip():
        return True, ""
    return False, ("the claimed fact is not stated in the source passages — "
                   "build the question ONLY from facts the passages explicitly state")
