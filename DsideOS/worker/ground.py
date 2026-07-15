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

# The grounding JUDGE. Default stays Anthropic/Haiku (battle-tested), but the
# provider is switchable so the gate can run on OpenAI (gpt-5.4-nano — ~4-5x
# cheaper, validated on a 50-case test to match Haiku once the prompt is
# tightened + few-shot). The judge must NOT be the drafting model (see .env:
# "the judge must not be the model being judged") — with GEN_PROVIDER=sarvam,
# an OpenAI or Anthropic judge both satisfy that.
GROUND_PROVIDER = os.environ.get("GROUND_PROVIDER", "anthropic").lower()
_DEFAULT_MODEL = ("gpt-5.4-nano" if GROUND_PROVIDER == "openai"
                  else "claude-haiku-4-5-20251001")
GROUND_MODEL = os.environ.get("GROUND_MODEL", _DEFAULT_MODEL)
GROUND = os.environ.get("GEN_GROUNDING", "1") == "1"

_SYSTEM = """# ROLE
You are a strict grounding checker for an exam-question generator. A separate
model wrote the question; your ONLY job is to decide whether the SOURCE PASSAGES
— and nothing else — prove the CLAIMED ANSWER is correct.

# OBJECTIVE
Protect students from wrong facts. A question you wrongly approve ships a false
fact to a real exam paper. When the passages do not clearly prove the answer,
your job is to REJECT it, even if you personally believe the answer is right.
Rejecting a good question only costs a retry; approving a bad one costs trust.

# METHOD (do this in order)
1. FIND THE QUOTE FIRST. Copy, verbatim, the single sentence from the passages
   that states the fact making the claimed answer correct. Copy it exactly as
   written — do not paraphrase, translate, or complete it.
2. THEN DECIDE. Only after you have a real verbatim quote in hand may you set
   "supported": true. If step 1 produced nothing — no sentence in the passages
   states the fact — then "supported" is false and "quote" is "".

# HARD RULES
- Use ONLY the passages. Your own knowledge is irrelevant and must be ignored.
- A quote must be a real substring of a passage. If you cannot find one, the
  answer is NOT supported — do not invent or reconstruct a sentence.
- "Topic is discussed" is NOT support. The passage must contain the SPECIFIC
  fact (the exact name / year / place / pairing the answer asserts). A passage
  that talks around the subject without stating the fact = not supported.
- match / order / statement questions: EVERY pairing, the FULL sequence, or
  EVERY statement must be individually supported by a quote. One unsupported
  element = the whole question is not supported.
- When genuinely unsure, choose false. Uncertainty is a rejection.

# EXAMPLES (how to decide — study these patterns)
PASSAGE: "चंद वंश की प्रारंभिक राजधानी चम्पावत थी। लगभग 1563 ई0 में कल्याण चंद ने राजधानी अल्मोड़ा स्थानांतरित की।"
Q: चंद वंश की राजधानी चम्पावत से अल्मोड़ा किसने स्थानांतरित की? ANSWER: कल्याण चंद
→ {"quote": "लगभग 1563 ई0 में कल्याण चंद ने राजधानी अल्मोड़ा स्थानांतरित की।", "supported": true}

PASSAGE: "चंद वंश की प्रारंभिक राजधानी चम्पावत थी। लगभग 1563 ई0 में कल्याण चंद ने राजधानी अल्मोड़ा स्थानांतरित की।"
Q: चंद वंश की राजधानी किसने स्थानांतरित की? ANSWER: सोमचंद
→ {"quote": "", "supported": false}   (passage names कल्याण चंद, not सोमचंद)

PASSAGE: "गैर आइनी- कुमाऊँ को बंगाल प्रेसीडेंसी के कानूनों से मुक्त रखा गया, यहाँ नॉन रेग्यूलेशन (गैर आइनी) प्रशासन लागू किया गया।"
Q: ब्रिटिश कुमाऊँ का प्रशासनिक स्वरूप क्या था? ANSWER: गैर-विनियित क्षेत्र (Non-Regulation)
→ {"quote": "यहाँ नॉन रेग्यूलेशन (गैर आइनी) प्रशासन लागू किया गया।", "supported": true}

PASSAGE: "उत्तराखंड क्रांति दल एक क्षेत्रीय राजनीतिक दल है जिसने पृथक राज्य आंदोलन में भूमिका निभाई। 24-25 जुलाई 1979 को मसूरी में इसका गठन हुआ।"
Q: उत्तराखंड क्रांति दल के प्रथम अध्यक्ष कौन थे? ANSWER: दिवाकर भट्ट
→ {"quote": "", "supported": false}   (passage discusses UKD's founding but NEVER names its first president — topic present, fact absent)

PASSAGE: "छवाड़सिंह नेगी के नेतृत्व में कुछ लोगों ने हरिद्वार से रामनगर तक लकड़ियों को जलाने की योजना बनाई। पौड़ी में नवयुवकों ने भी प्रदर्शन किए।"
Q: पौड़ी में जुलूस का नेतृत्व किसने किया? ANSWER: छवाड़सिंह नेगी
→ {"quote": "", "supported": false}   (छवाड़सिंह led the Haridwar-Ramnagar wood-burning plan, NOT the Pauri procession — passage does not name who led Pauri)

PASSAGE: "1916 ई0 में गोविन्दबल्लभ पंत आदि ने कुमाऊँ परिषद् की स्थापना की। इसका प्रथम अधिवेशन 1917 में अल्मोड़ा में हुआ जिसकी अध्यक्षता जयदत्त जोशी ने की।"
Q: कुमाऊँ परिषद् के प्रथम अधिवेशन की अध्यक्षता किसने की? ANSWER: जयदत्त जोशी
→ {"quote": "इसका प्रथम अधिवेशन 1917 में अल्मोड़ा में हुआ जिसकी अध्यक्षता जयदत्त जोशी ने की।", "supported": true}

PASSAGE: "1916 ई0 में गोविन्दबल्लभ पंत आदि ने कुमाऊँ परिषद् की स्थापना की। इसका प्रथम अधिवेशन 1917 में अल्मोड़ा में हुआ।"
Q: कुमाऊँ परिषद् का हल्द्वानी अधिवेशन किस वर्ष हुआ? ANSWER: 1918
→ {"quote": "", "supported": false}   (passage gives the 1917 Almora session; says nothing about a Haldwani session or 1918)

PASSAGE: "सूची में: a. कत्यूरी → सुभिक्षराजदेव, b. चंद → सोमचंद। परमारों ने गढ़वाल में तथा चन्दों ने कुमाऊँ में राज्य स्थापित किया।"
Q: सुमेलित करें: कत्यूरी-सुभिक्षराजदेव, चंद-सोमचंद, परमार-गढ़वाल  ANSWER: सभी सही
→ {"quote": "a. कत्यूरी → सुभिक्षराजदेव, b. चंद → सोमचंद ... परमारों ने गढ़वाल में", "supported": true}   (EVERY pairing is stated)

PASSAGE: "कत्यूरी → सुभिक्षराजदेव, चंद → सोमचंद।"
Q: सुमेलित करें: कत्यूरी-सुभिक्षराजदेव, चंद-सोमचंद, परमार-अजयपाल  ANSWER: सभी सही
→ {"quote": "", "supported": false}   (कत्यूरी and चंद pairings are stated, but परमार-अजयपाल is NOT — one unsupported pairing fails the whole question)

PASSAGE: "गढ़वाल में जयानंद भारती ने डोला पालकी आंदोलन विकसित किया, जो दलितों के विवाह में पालकी के अधिकार का आंदोलन था।"
Q: डोला पालकी आंदोलन के प्रणेता कौन थे? ANSWER: जयानंद भारती
→ {"quote": "गढ़वाल में जयानंद भारती ने डोला पालकी आंदोलन विकसित किया", "supported": true}

# OUTPUT
Return ONLY this JSON (no prose, no fences):
{"quote": "<verbatim source sentence, or empty>", "supported": true|false}"""

_USER = """SOURCE PASSAGES (your ONLY evidence):
{passages}

QUESTION:
{question}

CLAIMED ANSWER: ({answer}) {answer_text}
{claim_line}
Reminder: quote the exact supporting sentence FIRST; if you cannot quote it
verbatim from the passages above, "supported" is false. JSON only."""

_client: anthropic.Anthropic | None = None
_oai_client = None


def _anthropic() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(timeout=60, max_retries=3)
    return _client


def _openai():
    global _oai_client
    if _oai_client is None:
        from openai import OpenAI
        _oai_client = OpenAI(timeout=60, max_retries=3)
    return _oai_client


def _run_judge(system: str, user: str) -> str:
    """Call the configured grounding judge and return its raw text reply.
    Provider-switched: Anthropic (system/messages) or OpenAI chat (system+user
    as two messages). Both return the same quote-first JSON the parser expects."""
    if GROUND_PROVIDER == "openai":
        r = _openai().chat.completions.create(
            model=GROUND_MODEL, max_completion_tokens=2000,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        return (r.choices[0].message.content or "").strip()
    msg = _anthropic().messages.create(
        model=GROUND_MODEL, max_tokens=300,
        system=system, messages=[{"role": "user", "content": user}])
    return msg.content[0].text.strip() if msg.content else ""


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
        raw = _run_judge(_SYSTEM, _USER.format(
            passages=ptxt, question=_question_text(q),
            answer=ans, answer_text=answer_text, claim_line=claim_line))
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
