# -*- coding: utf-8 -*-
"""
Agentic answer extraction — search+scrape loop driven by Claude.

Claude runs in a while loop. Each iteration it:
  1. Decides what to search next (or declares it is done).
  2. We run that search + scrape.
  3. Claude reads the new page(s) and either answers confidently or
     asks for another search with a better/different query.

Simple questions (Q5 — "who founded Almora?") exit after 1 iteration.
Complex questions (Q9 — unmatched pairs, assertion-style) naturally run
2-4 iterations as Claude searches each claim separately.

Cap: MAX_ITERATIONS prevents runaway. If still unresolved after the cap,
Claude is asked to reason from everything it has seen so far (no web
source) — the answer is flagged "reasoning_only" so Mayank can verify.

Import-safe for the web dashboard:
    from extract import extract_answer
    result = await extract_answer(stem, options)   # -> ExtractResult

CLI:
    python extract.py "<stem>" "optA" "optB" "optC" "optD"
    python extract.py --json <file.json> [--live] [--only 4,7,12]
"""

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from scrape import scrape_page
from search import PRIORITY_DOMAINS, SearchResult, search_web

BASE = Path(__file__).resolve().parents[1]
MODEL = "claude-opus-4-8"
LABELS = ["a", "b", "c", "d", "e", "f"]

MAX_ITERATIONS = 5       # hard cap on search iterations per question
MAX_SCRAPE = 2           # pages to scrape per iteration (top priority ones)
MAX_PAGE_CHARS = 5000    # chars per page fed to Claude


# ---------------------------------------------------------------------------
# env / client
# ---------------------------------------------------------------------------
def _load_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env = BASE.parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
                return


_client: anthropic.Anthropic | None = None


def _client_get() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _load_key()
        _client = anthropic.Anthropic()
    return _client


# ---------------------------------------------------------------------------
# result
# ---------------------------------------------------------------------------
@dataclass
class ExtractResult:
    answer: str           # option letter: a/b/c/...
    confidence: str       # high | medium | low | reasoning_only
    reason: str           # one-line justification (Hindi ok)
    source_url: str       # exact URL the answer came from (empty if reasoning_only)
    source_domain: str
    iterations: int       # how many search iterations were needed
    all_sources: list = field(default_factory=list)   # every URL scraped across all iters
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "confidence": self.confidence,
            "reason": self.reason,
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "iterations": self.iterations,
            "all_sources": self.all_sources,
            "error": self.error,
        }


def _fail(msg: str, iters: int = 0, sources: list | None = None) -> ExtractResult:
    return ExtractResult(
        answer="", confidence="low", reason="", source_url="",
        source_domain="", iterations=iters,
        all_sources=sources or [], error=msg,
    )


# ---------------------------------------------------------------------------
# the agent system prompt
# ---------------------------------------------------------------------------
AGENT_SYSTEM = """You are an agentic answer verifier for Indian competitive exams \
(UKSSSC Uttarakhand Patwari/Lekhpal). Your job is to find the correct option for \
an MCQ by directing web searches and reading the results.

You run in a loop. Each turn you receive the question + options + everything \
scraped so far, and you output a JSON object with one of two shapes:

SHAPE A — you need more information:
{
  "status": "searching",
  "query": "<exact search string to run next>",
  "reasoning": "<one line: what you still need to verify and why>"
}

SHAPE B — you are confident (or have reached the iteration limit):
{
  "status": "done",
  "answer": "<option letter a/b/c/d>",
  "confidence": "high" | "medium" | "low" | "reasoning_only",
  "reason": "<one line in Hindi or English citing the source>",
  "source_url": ""
}

Rules:
- For simple factual MCQs: one good search is usually enough → output SHAPE B fast.
- For matching/assertion MCQs (सुमेलित, असुमेलित, सूची, कथन): search each \
  pair/claim SEPARATELY across multiple iterations — do NOT try to resolve all \
  pairs with one broad query.
- Use "reasoning_only" confidence only when you have exhausted searches and \
  must fall back to your own knowledge. Always try at least 2 searches first.
- Keep queries SHORT and entity-focused (Hindi is fine). Drop MCQ filler words.
- Output ONLY the JSON object. No prose, no markdown fences."""


def _build_turn(
    stem: str,
    options: list[str],
    history: list[dict],   # [{"query": ..., "pages": [(url, text), ...]}, ...]
    at_limit: bool,
) -> str:
    opts = "\n".join(f"  ({LABELS[i]}) {o}" for i, o in enumerate(options))
    parts = [f"Question:\n{stem}\n\nOptions:\n{opts}"]

    if not history:
        parts.append("\nNo searches run yet. Decide your first search query.")
    else:
        parts.append(f"\n--- Search history ({len(history)} iteration(s)) ---")
        for i, entry in enumerate(history):
            parts.append(f"\nIteration {i+1} query: {entry['query']}")
            for j, (url, text) in enumerate(entry["pages"]):
                parts.append(f"  Page [{i}.{j}] {url}\n  {text[:MAX_PAGE_CHARS]}")

    if at_limit:
        parts.append(
            "\n\nYou have reached the search limit. "
            "Answer now using everything above plus your own knowledge if needed. "
            "Set confidence='reasoning_only' if you had to rely on your own knowledge."
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# one Claude call — returns parsed dict or None
# ---------------------------------------------------------------------------
def _call_agent(messages: list[dict]) -> dict | None:
    msg = _client_get().messages.create(
        model=MODEL,
        max_tokens=512,
        thinking={"type": "adaptive"},
        system=AGENT_SYSTEM,
        messages=messages,
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    # strip markdown fences if Claude wraps it anyway
    text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# search + scrape helper
# ---------------------------------------------------------------------------
async def _fetch_pages(query: str) -> tuple[list[SearchResult], list[tuple[str, str]]]:
    """Search → scrape top priority URLs. Returns (results, [(url, text)])."""
    results = await search_web(query, num_results=8)
    priority = [r for r in results if r.priority < len(PRIORITY_DOMAINS)]
    to_scrape = (priority or results)[:MAX_SCRAPE]

    pages: list[tuple[str, str]] = []
    for r in to_scrape:
        try:
            text = await scrape_page(r.url)
            if text and text.strip():
                pages.append((r.url, text))
        except Exception as e:
            print(f"   [scrape failed {r.domain}: {e}]")
    return results, pages


# ---------------------------------------------------------------------------
# main agentic loop
# ---------------------------------------------------------------------------
async def extract_answer(stem: str, options: list[str]) -> ExtractResult:
    history: list[dict] = []
    all_sources: list[str] = []
    messages: list[dict] = []

    for iteration in range(MAX_ITERATIONS + 1):  # +1 for the forced-final call
        at_limit = iteration >= MAX_ITERATIONS
        turn_text = _build_turn(stem, options, history, at_limit)

        messages = [{"role": "user", "content": turn_text}]
        verdict = await asyncio.to_thread(_call_agent, messages)

        if verdict is None:
            # parse failed — force one more attempt with explicit JSON reminder
            messages.append({
                "role": "user",
                "content": "Your response was not valid JSON. Output ONLY the JSON object, no other text."
            })
            verdict = await asyncio.to_thread(_call_agent, messages)
            if verdict is None:
                return _fail("agent returned no parseable JSON after retry", iteration, all_sources)

        status = verdict.get("status", "")

        if status == "searching" and not at_limit:
            query = str(verdict.get("query", "")).strip()
            reasoning = verdict.get("reasoning", "")
            if not query:
                return _fail("agent returned empty query", iteration, all_sources)
            print(f"  [iter {iteration+1}] query: {query}")
            if reasoning:
                print(f"           reason: {reasoning}")

            results, pages = await _fetch_pages(query)
            all_sources.extend(url for url, _ in pages)
            history.append({"query": query, "pages": pages})

            if not pages:
                print(f"   [no pages scraped for this query]")
            continue   # next iteration

        # status == "done" (or at_limit forced it)
        ans = str(verdict.get("answer", "")).lower()
        if ans not in LABELS[: len(options)]:
            return _fail(f"invalid answer letter: {ans!r}", iteration + 1, all_sources)

        confidence = str(verdict.get("confidence", "low")).lower()
        reason = str(verdict.get("reason", "")).strip()

        # source_url = first page from the first iteration that had results
        # (highest-priority site, since search results are priority-sorted).
        # all_sources already contains every URL scraped across all iterations.
        # Only use the source URL if it's from a trusted priority domain.
        # Discard garbage URLs (Bing redirects, unrelated sites) that slip through.
        trusted = [u for u in all_sources
                   if any(d in u for d in PRIORITY_DOMAINS)]
        src_url = trusted[0] if trusted else (all_sources[0] if all_sources else "")

        src_domain = re.sub(r"https?://(www\.)?", "", src_url).split("/")[0] if src_url else ""

        # No trusted source found — downgrade confidence so it gets flagged
        if not src_url and confidence not in ("reasoning_only", "low"):
            confidence = "low"

        return ExtractResult(
            answer=ans,
            confidence=confidence,
            reason=reason,
            source_url=src_url,
            source_domain=src_domain,
            iterations=iteration + 1,
            all_sources=all_sources,
        )

    return _fail(f"exhausted {MAX_ITERATIONS} iterations without answer", MAX_ITERATIONS, all_sources)


# ---------------------------------------------------------------------------
# write-back into questions JSON
# ---------------------------------------------------------------------------
def apply_to_question(q: dict, res: ExtractResult) -> str:
    if res.error:
        q["flag"] = f"AI निष्कर्षण विफल ({res.error}) — Mayank स्वयं जाँचें।"
        return "failed"
    q["answer"] = res.answer
    q["reason"] = res.reason
    q["sources"] = [res.source_url] if res.source_url else []
    q["source_domain"] = res.source_domain
    q["source_url"] = res.source_url
    q["iterations"] = res.iterations
    q["all_sources"] = res.all_sources
    if res.confidence in ("high", "medium") and res.source_url:
        q.pop("flag", None)
        return "confirmed"
    q["flag"] = f"AI confidence={res.confidence} — Mayank पुष्टि करें।"
    return "weak"


async def run_json(path: Path, live: bool, only: set[int] | None) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    qs = [q for q in data["questions"] if only is None or q["n"] in only]
    print(f"{len(data['questions'])} questions; {len(qs)} to extract.")

    if not live:
        print("\nDRY PLAN (no API). Re-run with --live to extract via Claude.")
        for q in qs[:5]:
            print(f"  Q{q['n']}: {q['stem'][:80]}...")
        return

    tally = {"confirmed": 0, "weak": 0, "failed": 0}
    for q in qs:
        print(f"\n--- Q{q['n']} ---")
        res = await extract_answer(q["stem"], q.get("options") or [])
        status = apply_to_question(q, res)
        tally[status] += 1
        mark = {"confirmed": "OK", "weak": "??", "failed": "XX"}[status]
        print(f"  [{mark}] answer={res.answer or '-'} conf={res.confidence} "
              f"iters={res.iterations} src={res.source_domain or '-'}")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nDone. {tally}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]

    if "--json" in args:
        i = args.index("--json")
        path = Path(args[i + 1])
        live = "--live" in args
        only = None
        if "--only" in args:
            only = {int(x) for x in args[args.index("--only") + 1].split(",")}
        asyncio.run(run_json(path, live, only))
        return

    if len(args) < 2:
        print('usage: python extract.py "<stem>" "optA" "optB" ...')
        print('       python extract.py --json <file.json> [--live] [--only 4,7]')
        sys.exit(1)

    stem, options = args[0], args[1:]

    async def one():
        res = await extract_answer(stem, options)
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))

    asyncio.run(one())


if __name__ == "__main__":
    main()
