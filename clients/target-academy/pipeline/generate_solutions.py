# -*- coding: utf-8 -*-
"""Generate complete solutions (answer + विस्तृत व्याख्या) for any questions JSON.

Two modes, detected automatically from the JSON:

  answer_source = "official_key"  →  EXPLAIN mode
      Answers are already confirmed. Just prove why each answer is correct
      (3-5 sentence Hindi explanation). Web search used for factual backing.

  answer_source = null / missing   →  FIND + EXPLAIN mode
      No official key. Independently determine the correct answer via web
      search, then explain it. Writes q["answer"] + q["solution"] + q["sources"].

Both modes write q["solution"]. Re-runnable: questions with a non-empty
"solution" are skipped. Use --force to regenerate all.

The output JSON feeds directly into run_pipeline.py → Solution (Teacher).docx.

Usage:
    python generate_solutions.py <questions.json>                  # dry plan
    python generate_solutions.py <questions.json> --live           # call API
    python generate_solutions.py <questions.json> --live --only 1,5,12
    python generate_solutions.py <questions.json> --live --batch 20
    python generate_solutions.py <questions.json> --live --force   # redo all
"""

import json
import os
import re
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PIPELINE = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE))
from llm import MODELS  # noqa: E402

# This script uses Anthropic's web_search tool directly (no OpenAI equivalent),
# so it pins concrete Anthropic models rather than the provider-routed tiers.
ANTH_FAST  = MODELS["anthropic"]["fast"]
ANTH_SMART = MODELS["anthropic"]["smart"]

MAX_WEB_USES = 5

# Reasoning/maths keywords — these questions get Sonnet; everything else gets Haiku.
_REASONING_KEYWORDS = (
    "श्रृंखला", "अनुक्रम", "pattern", "series", "यदि", "हल", "गणना",
    "कितना", "कितने", "अनुपात", "ratio", "profit", "loss", "लाभ", "हानि",
    "speed", "distance", "time", "चाल", "दूरी", "समय", "average", "औसत",
    "percentage", "प्रतिशत", "angle", "कोण", "triangle", "वर्ग", "area",
    "कथन", "assertion", "reason", "निष्कर्ष", "conclusion",
)
LABELS = ["a", "b", "c", "d", "e", "f"]

# ── system prompts ──────────────────────────────────────────────────────────

SYSTEM_EXPLAIN = """Indian competitive-exam teacher. The correct answer is given.
Write 3-4 sentences in Hindi (Devanagari) explaining WHY it is correct and why
key distractors are wrong. English proper nouns stay in English. No "विस्तृत व्याख्या:" prefix.
Return ONLY JSON: {"solution": "<Hindi>", "sources": ["domain1"]}"""

SYSTEM_FIND_AND_EXPLAIN = """Indian competitive-exam solver. Find the correct MCQ
option via web search, then write 3-4 sentences in Hindi explaining why it is correct.
Use ≥2 reliable sources. Flag low confidence. English proper nouns stay in English.
Return ONLY JSON:
{"answer":"a|b|c|d","confidence":"high|medium|low","solution":"<Hindi>","sources":["d1","d2"],"flag":"<optional>"}"""

USER_EXPLAIN = """प्रश्न {n}: {stem}

विकल्प:
{opts}

सही उत्तर: ({answer_label}) {answer_text}

इस उत्तर की विस्तृत व्याख्या हिंदी में लिखें।"""

USER_FIND = """प्रश्न {n}: {stem}

विकल्प:
{opts}

सही उत्तर खोजें और हिंदी में विस्तृत व्याख्या लिखें।"""


# ── helpers ─────────────────────────────────────────────────────────────────

def _model_for(q):
    """Haiku for factual GK; Sonnet for reasoning/maths/assertion questions."""
    text = (q.get("stem") or "").lower()
    if any(kw in text for kw in _REASONING_KEYWORDS):
        return ANTH_SMART
    return ANTH_FAST


def _opt_lines(q):
    return "\n".join(f"  ({LABELS[i].upper()}) {o}"
                     for i, o in enumerate(q.get("options") or []))


def _answer_text(q):
    ans = str(q.get("answer", "")).lower()
    idx = LABELS.index(ans) if ans in LABELS else -1
    opts = q.get("options") or []
    return opts[idx] if 0 <= idx < len(opts) else "?"


def _extract_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ── Claude calls ─────────────────────────────────────────────────────────────

def _call(client, system, user, model=ANTH_FAST):
    msg = client.messages.create(
        model=model,
        max_tokens=512,
        system=system,
        tools=[{"type": "web_search_20250305", "name": "web_search",
                "max_uses": MAX_WEB_USES}],
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return _extract_json(text)


def call_explain(client, q):
    user = USER_EXPLAIN.format(
        n=q["n"],
        stem=q["stem"],
        opts=_opt_lines(q),
        answer_label=str(q.get("answer", "")).upper(),
        answer_text=_answer_text(q),
    )
    return _call(client, SYSTEM_EXPLAIN, user, model=_model_for(q))


def call_find_and_explain(client, q):
    user = USER_FIND.format(n=q["n"], stem=q["stem"], opts=_opt_lines(q))
    return _call(client, SYSTEM_FIND_AND_EXPLAIN, user, model=_model_for(q))


# ── apply result back to question ────────────────────────────────────────────

def apply_explain(q, result):
    """EXPLAIN mode: answer already set, just need solution text."""
    if not result or not result.get("solution"):
        q.setdefault("flag", "व्याख्या उत्पन्न नहीं हुई — Mayank जाँचें।")
        return "failed"
    q["solution"] = result["solution"].strip()
    srcs = [s.lower() for s in (result.get("sources") or [])]
    if srcs:
        q["sources"] = srcs
    q.pop("flag", None)
    return "ok"


def apply_find(q, result):
    """FIND+EXPLAIN mode: set answer, solution, sources, and flag if weak."""
    if not result or not result.get("solution"):
        q.setdefault("flag", "उत्तर और व्याख्या उत्पन्न नहीं हुए — Mayank जाँचें।")
        return "failed"
    ans = str(result.get("answer", "")).lower()
    if ans in LABELS[: len(q.get("options") or [])]:
        q["answer"] = ans
    q["solution"] = result["solution"].strip()
    srcs = [s.lower() for s in (result.get("sources") or [])]
    if srcs:
        q["sources"] = srcs
    conf = result.get("confidence", "low")
    flag = result.get("flag")
    if flag:
        q["flag"] = flag
    elif conf == "low" or len(srcs) < 2:
        q["flag"] = f"AI confidence={conf}, स्रोत={len(srcs)} — Mayank पुष्टि करें।"
    else:
        q.pop("flag", None)
    return "ok" if not q.get("flag") else "weak"


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("usage: python generate_solutions.py <questions.json> "
              "[--live] [--only 1,2,3] [--batch N] [--force]")
        sys.exit(1)

    path = Path(sys.argv[1])
    live  = "--live"  in sys.argv
    force = "--force" in sys.argv

    only = None
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = {int(x) for x in sys.argv[i + 1].split(",")}

    batch_size = None
    if "--batch" in sys.argv:
        i = sys.argv.index("--batch")
        batch_size = int(sys.argv[i + 1])

    data = json.loads(path.read_text(encoding="utf-8"))
    official = data.get("answer_source") == "official_key"
    mode = "EXPLAIN" if official else "FIND+EXPLAIN"

    def needs_work(q):
        if force:
            return True
        if not official and not q.get("answer"):
            return True
        return not q.get("solution")

    todo = [q for q in data["questions"]
            if needs_work(q) and (only is None or q["n"] in only)]
    if batch_size:
        todo = todo[:batch_size]

    already = len(data["questions"]) - len(todo) if not only else "n/a"
    print(f"Mode: {mode}  |  {len(data['questions'])} questions total  |  "
          f"{len(todo)} to process  |  {already} already done")

    if not live:
        print("\nDRY PLAN — re-run with --live to call the API.")
        for q in todo[:10]:
            print(f"  Q{q['n']}: {q['stem'][:70]}...")
        if len(todo) > 10:
            print(f"  ... and {len(todo) - 10} more")
        return

    # load API key
    env = BASE.parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ANTHROPIC_API_KEY=") and "ANTHROPIC_API_KEY" not in os.environ:
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
    import anthropic
    client = anthropic.Anthropic()

    tally = {"ok": 0, "weak": 0, "failed": 0}
    for i, q in enumerate(todo, 1):
        try:
            if official:
                result  = call_explain(client, q)
                outcome = apply_explain(q, result)
            else:
                result  = call_find_and_explain(client, q)
                outcome = apply_find(q, result)
        except Exception as e:
            q["flag"] = f"त्रुटि — {type(e).__name__}: {e}"
            outcome = "failed"

        tally[outcome] += 1
        model_used = "haiku" if _model_for(q) == ANTH_FAST else "sonnet"
        preview = (q.get("solution") or "")[:50]
        print(f"  [{i}/{len(todo)}] Q{q['n']} [{model_used}][{outcome}] — {preview}...")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(0.3)

    done = tally["ok"] + tally["weak"]
    print(f"\nDone. ok={tally['ok']}  weak={tally['weak']}  failed={tally['failed']}")
    if tally["weak"]:
        flagged = [q["n"] for q in data["questions"] if q.get("flag")]
        print(f"Flagged for Mayank review: Q{flagged}")
    print(f"JSON updated: {path}")
    print(f"Next: python run_pipeline.py")


if __name__ == "__main__":
    main()
