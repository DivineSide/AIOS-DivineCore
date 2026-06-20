# -*- coding: utf-8 -*-
"""AI-driven answer verification — a re-runnable pipeline step.

For each FACTUAL question it asks Claude (with web search) to independently
determine the correct option and cite the reliable sources it used, then writes
the verdict back into the questions JSON:
  - q["answer"]  : corrected to the verified option
  - q["sources"] : the sources Claude cited (>=2 reliable => confirmed/green ✔)
  - q["reason"]  : Claude's one-line justification
  - q["flag"]    : kept/added when verification was weak (single source / low
                   confidence / sources disagree)

Questions with a worked "solution" (reasoning/maths) are SKIPPED — they are
self-verifying and need no external source (per the locked doctrine).

Cost model: uses the Anthropic API (web search tool). This is the PRODUCTIZATION
path — metered, ~$0.01-0.03 per question incl. web search. For now generation
runs on Claude Code plan usage; flip RUN_LIVE=True (and have ANTHROPIC_API_KEY
in .env) to actually call the API.

Topic-aware source guidance is injected into the prompt so UK-specific questions
get checked against Uttarakhand sources, national ones against national sources.

Usage:
    python verify_answers_ai.py <questions.json>            # dry plan (no API)
    python verify_answers_ai.py <questions.json> --live     # call the API
    python verify_answers_ai.py <questions.json> --live --only 1,2,3
"""
import json
import os
import re
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MODEL = "claude-sonnet-4-6"          # latest Sonnet; swap per LLM-core routing
MAX_WEB_USES = 4                      # web searches allowed per question

LABELS = ["a", "b", "c", "d", "e", "f"]

SYSTEM = """You are a meticulous Indian competitive-exam answer verifier for a \
UKSSSC (Uttarakhand) Patwari/Lekhpal paper. For the given MCQ you must determine \
the SINGLE correct option using web search, and report the reliable sources you \
used. Be honest about uncertainty.

Source discipline (use the right tier for the topic):
- National GK (Indian polity/history/geography/science/current affairs):
  prefer testbook.com, theexampillar.com, adda247.com, NCERT, Britannica, Wikipedia.
- Uttarakhand-specific GK (UK history/geography/culture/schemes/personalities):
  prefer theexampillar.com (UK section), uttarakhandexamsgk.com, studyfry.com,
  gktoday.in UK quizzes, and authoritative UK GK references.
Reasoning/maths should be solved, not searched.

Return ONLY a JSON object, no prose:
{"answer":"a|b|c|d|e","confidence":"high|medium|low","sources":["domain1","domain2"],"reason":"<=160 chars Hindi or English"}
- "sources": list the DOMAINS you actually relied on (>=2 independent reliable
  ones if you are confident). If you could not confirm, return your best guess
  with confidence "low" and whatever single source (or []) you found."""

USER_TMPL = """Question {n}: {stem}
Options:
{opts}

Draft answer (unverified): ({draft})
Verify the correct option via web search and return the JSON verdict."""


def is_factual(q):
    """Skip self-verifying reasoning/maths (they carry a worked solution)."""
    return not q.get("solution")


def build_user(q):
    opts = "\n".join(f"  ({LABELS[i]}) {o}" for i, o in enumerate(q.get("options") or []))
    return USER_TMPL.format(n=q["n"], stem=q["stem"], opts=opts,
                            draft=str(q.get("answer", "?")))


def call_claude(client, q):
    """One verification call with the web-search tool. Returns verdict dict."""
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search",
                "max_uses": MAX_WEB_USES}],
        messages=[{"role": "user", "content": build_user(q)}],
    )
    # collect final text; extract the JSON verdict
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def apply_verdict(q, v):
    if not v:
        q["flag"] = "AI सत्यापन विफल — Mayank स्वयं जाँचें।"
        return "failed"
    ans = str(v.get("answer", "")).lower()
    if ans in LABELS[: len(q.get("options") or [])]:
        q["answer"] = ans
    srcs = [s.lower() for s in (v.get("sources") or [])]
    q["sources"] = srcs
    if v.get("reason"):
        q["reason"] = v["reason"]
    if len(srcs) >= 2 and v.get("confidence") in ("high", "medium"):
        q.pop("flag", None)
        return "confirmed"
    q["flag"] = (f"AI confidence={v.get('confidence','low')}, "
                 f"स्रोत={len(srcs)} — Mayank पुष्टि करें।")
    return "weak"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("usage: python verify_answers_ai.py <questions.json> [--live] [--only 1,2,3]")
        sys.exit(1)
    path = Path(sys.argv[1])
    live = "--live" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = {int(x) for x in sys.argv[sys.argv.index("--only") + 1].split(",")}

    data = json.loads(path.read_text(encoding="utf-8"))
    factual = [q for q in data["questions"] if is_factual(q)
               and (only is None or q["n"] in only)]
    skipped = len(data["questions"]) - len([q for q in data["questions"] if is_factual(q)])
    print(f"{len(data['questions'])} questions; {len(factual)} factual to verify; "
          f"{skipped} self-verifying (skipped).")

    if not live:
        print("\nDRY PLAN (no API call). Re-run with --live to verify via Claude+web.")
        print("When productized this loops every factual Q through call_claude().")
        return

    # load key from .env
    env = BASE.parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY=") and "ANTHROPIC_API_KEY" not in os.environ:
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
    import anthropic
    client = anthropic.Anthropic()

    tally = {"confirmed": 0, "weak": 0, "failed": 0}
    for i, q in enumerate(factual, 1):
        try:
            v = call_claude(client, q)
            outcome = apply_verdict(q, v)
        except Exception as e:
            q["flag"] = f"AI सत्यापन त्रुटि — Mayank जाँचें ({type(e).__name__})."
            outcome = "failed"
        tally[outcome] += 1
        print(f"  [{i}/{len(factual)}] Q{q['n']}: {outcome} -> ({q.get('answer')}) "
              f"src={q.get('sources')}")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(0.5)

    print(f"\nDone. confirmed={tally['confirmed']} weak={tally['weak']} "
          f"failed={tally['failed']}. JSON updated: {path.name}")


if __name__ == "__main__":
    main()
