# -*- coding: utf-8 -*-
"""
Question fetcher — three sources, one unified output.

Source 1 — PYQs (web-scraped)
  Search testbook/theexampillar/etc. for past exam questions on a topic.
  Answers come embedded in the scraped page → used as-is, source URL logged.

Source 2 — Question banks (web-scraped)
  Same sites have topic-wise practice banks (not tied to a paper date).
  Same pipeline, different query pattern.

Source 3 — AI-generated
  Claude generates questions grounded in:
    (a) the institute's corpus (corpus/parsed/*.md)
    (b) a sample of real PYQs from Sources 1+2 (pattern/difficulty reference)
  No answer attached → run through extract.py for verification.
  If extract returns low confidence → drop and regenerate.

Final output: questions JSON in the same schema as existing papers:
  {"questions": [{"n": 1, "stem": "...", "options": [...], "answer": "a",
                  "reason": "...", "sources": ["url"], "source_type": "pyq|bank|ai"}]}

The 33/33/33 split is the default. Adjust with --pyq-n / --bank-n / --ai-n.

CLI:
    python fetch_questions.py "पंवार वंश" --total 30 --out review/panwar-paper.json
    python fetch_questions.py "कुमाऊँ का इतिहास" --total 15 --pyq-n 5 --bank-n 5 --ai-n 5
    python fetch_questions.py "उत्तराखण्ड भूगोल" --total 9 --dry   # plan only, no API

Import:
    from fetch_questions import fetch_all
    questions = await fetch_all(topic, total=30)
"""

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from extract import extract_answer
from scrape import scrape_page
from search import PRIORITY_DOMAINS, search_web

BASE = Path(__file__).resolve().parents[1]
MODEL = "claude-opus-4-8"
LABELS = ["a", "b", "c", "d"]

# Corpus files loaded once for AI generation
CORPUS_DIR = BASE / "corpus" / "parsed"
PYQ_DIR = BASE / "corpus" / "pyq"

MAX_SCRAPE_PER_QUERY = 3     # pages to scrape per search query
MAX_PAGE_CHARS = 6000        # chars per page fed to Claude for parsing
AI_REGEN_ATTEMPTS = 3        # retries if AI question fails verification


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
# shared question schema
# ---------------------------------------------------------------------------
@dataclass
class Question:
    n: int
    stem: str
    options: list[str]
    answer: str           # option letter a/b/c/d
    reason: str
    sources: list[str]    # URLs or site names
    source_type: str      # "pyq" | "bank" | "ai"
    confidence: str = "high"

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "stem": self.stem,
            "options": self.options,
            "answer": self.answer,
            "reason": self.reason,
            "sources": self.sources,
            "source_type": self.source_type,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# SOURCE 1 + 2 — scrape questions from exam sites
# ---------------------------------------------------------------------------

# Claude parses raw scraped page text into structured questions.
# Used for both PYQ pages and question-bank pages.
PARSE_SYSTEM = """You extract MCQ questions from raw scraped text of an Indian \
exam preparation website (UKSSSC Uttarakhand Patwari/Lekhpal).

Return ONLY a JSON array of question objects. Each object:
{
  "stem": "<question text, Hindi ok>",
  "options": ["<opt a>", "<opt b>", "<opt c>", "<opt d>"],
  "answer": "<letter a/b/c/d>",
  "reason": "<one line explanation if present, else empty string>"
}

Rules:
- Include ONLY questions that have all four options AND a clear answer.
- Preserve Hindi text exactly as it appears.
- If the page has no valid MCQs, return an empty array [].
- Output ONLY the JSON array, no prose, no markdown fences."""


def _parse_questions_from_page(url: str, text: str) -> list[dict]:
    """Ask Claude to extract structured MCQs from scraped page text."""
    msg = _client_get().messages.create(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=PARSE_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"URL: {url}\n\nPage text:\n{text[:MAX_PAGE_CHARS]}"
        }],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
    # extract the JSON array
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
        return [q for q in items if q.get("stem") and q.get("options") and q.get("answer")]
    except json.JSONDecodeError:
        return []


def _dedup(existing: list[Question], candidates: list[dict]) -> list[dict]:
    """Drop candidates whose stem already exists (fuzzy: first 40 chars)."""
    seen = {q.stem[:40].strip() for q in existing}
    return [c for c in candidates if c["stem"][:40].strip() not in seen]


async def _scrape_source(
    topic: str,
    query_suffix: str,
    source_type: str,
    target_n: int,
    existing: list[Question],
    extra_queries: list[str] | None = None,
) -> list[Question]:
    """
    Search for `topic + query_suffix` (and any extra_queries), scrape, parse questions.
    source_type: "pyq" or "bank"
    """
    # No site: filter on primary — DDG drops results when site: combines with Hindi text.
    # Priority-domain reranking in search_web handles testbook/theexampillar preference.
    primary_query = f"{topic} {query_suffix} testbook theexampillar"
    all_queries = [primary_query] + (extra_queries or [])

    collected: list[Question] = []
    scraped_urls: set[str] = set()

    for query in all_queries:
        if len(collected) >= target_n:
            break
        print(f"\n[{source_type.upper()}] searching: {query}")
        results = await search_web(query, num_results=8)
        priority_results = [r for r in results if r.priority < len(PRIORITY_DOMAINS)]
        to_scrape = (priority_results or results)[:MAX_SCRAPE_PER_QUERY]

        for r in to_scrape:
            if len(collected) >= target_n:
                break
            if r.url in scraped_urls:
                continue
            scraped_urls.add(r.url)
            print(f"  scraping: {r.domain} — {r.url}")
            try:
                text = await scrape_page(r.url)
                if not text or not text.strip():
                    continue
                raw_qs = await asyncio.to_thread(_parse_questions_from_page, r.url, text)
                fresh = _dedup(existing + collected, raw_qs)
                print(f"    → {len(raw_qs)} parsed, {len(fresh)} new after dedup")
                for raw_q in fresh:
                    if len(collected) >= target_n:
                        break
                    collected.append(Question(
                        n=0,
                        stem=raw_q["stem"],
                        options=raw_q["options"],
                        answer=raw_q["answer"].lower(),
                        reason=raw_q.get("reason", ""),
                        sources=[r.url],
                        source_type=source_type,
                        confidence="high",
                    ))
            except Exception as e:
                print(f"    [scrape/parse failed: {e}]")

    print(f"  [{source_type.upper()}] collected {len(collected)}/{target_n}")
    return collected


# ---------------------------------------------------------------------------
# SOURCE 3 — AI-generated questions from corpus
# ---------------------------------------------------------------------------

def _load_corpus(topic: str) -> str:
    """Load relevant corpus files. Simple keyword match on filename."""
    topic_lower = topic.lower()
    chunks = []
    for md in list(CORPUS_DIR.glob("*.md")) + list(PYQ_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="ignore")
        # Include if topic keyword appears in the file (rough relevance)
        if any(kw in text[:3000] for kw in [topic, topic_lower]):
            chunks.append(f"--- {md.name} ---\n{text[:4000]}")
    if not chunks:
        # No match — load all PYQ files as pattern reference
        for md in PYQ_DIR.glob("*.md"):
            chunks.append(f"--- {md.name} ---\n{md.read_text(encoding='utf-8', errors='ignore')[:2000]}")
    return "\n\n".join(chunks[:6])  # cap at 6 files to keep context size sane


def _build_ai_gen_prompt(topic: str, n: int, corpus: str, pyq_samples: list[Question]) -> str:
    samples_text = ""
    if pyq_samples:
        sample_list = [
            f"Q: {q.stem}\n(a) {q.options[0]}  (b) {q.options[1]}  "
            f"(c) {q.options[2]}  (d) {q.options[3]}\nAnswer: ({q.answer})"
            for q in pyq_samples[:5]
        ]
        samples_text = "REAL PYQ SAMPLES (match this difficulty and pattern):\n" + "\n\n".join(sample_list)

    return f"""Generate exactly {n} original MCQ questions on the topic: {topic}

{samples_text}

CORPUS (use this as your factual source — do not invent facts not present here):
{corpus[:8000]}

Output ONLY a JSON array of {n} objects:
[
  {{
    "stem": "<question in Hindi>",
    "options": ["<a>", "<b>", "<c>", "<d>"],
    "answer": "<letter a/b/c/d>",
    "reason": "<one line: what in the corpus supports this answer>"
  }}
]

Rules:
- Every fact must be traceable to the corpus above.
- Match the difficulty and style of the PYQ samples exactly.
- Questions must be unique — no repeats from the samples.
- Options must have exactly one correct answer, three plausible distractors.
- Hindi for question stems; options can be Hindi or short English terms.
- Output ONLY the JSON array."""


AI_VERIFY_SYSTEM = """You are verifying an AI-generated MCQ against a corpus. \
The question was generated from this corpus — check if the answer is correct \
and the question is well-formed.

Return ONLY JSON:
{"valid": true/false, "corrected_answer": "<letter or same>", "issue": "<or empty>"}"""


async def _generate_ai_questions(
    topic: str,
    target_n: int,
    existing: list[Question],
) -> list[Question]:
    print(f"\n[AI] generating {target_n} questions on: {topic}")
    corpus = _load_corpus(topic)
    pyq_samples = [q for q in existing if q.source_type == "pyq"][:5]

    collected: list[Question] = []
    attempts = 0

    while len(collected) < target_n and attempts < AI_REGEN_ATTEMPTS:
        attempts += 1
        still_need = target_n - len(collected)
        print(f"  [AI attempt {attempts}] generating {still_need} questions...")

        prompt = _build_ai_gen_prompt(topic, still_need, corpus, pyq_samples)
        msg = _client_get().messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            print("  [AI] no parseable JSON array")
            continue

        try:
            items = json.loads(m.group(0))
        except json.JSONDecodeError:
            print("  [AI] JSON decode failed")
            continue

        fresh = _dedup(existing + collected, items)
        print(f"  [AI] {len(items)} generated, {len(fresh)} new after dedup")

        for raw_q in fresh:
            if len(collected) >= target_n:
                break
            stem = raw_q.get("stem", "")
            options = raw_q.get("options", [])
            if not stem or len(options) != 4:
                continue

            # Verify via extract.py — the quality gate for AI questions
            print(f"    verifying: {stem[:60]}...")
            res = await extract_answer(stem, options)
            if res.confidence in ("high", "medium"):
                collected.append(Question(
                    n=0,
                    stem=stem,
                    options=options,
                    answer=res.answer,
                    reason=res.reason,
                    sources=[res.source_url] if res.source_url else ["corpus"],
                    source_type="ai",
                    confidence=res.confidence,
                ))
                print(f"    ✓ verified ({res.confidence}) → answer={res.answer}")
            else:
                print(f"    ✗ dropped (confidence={res.confidence}) — will regenerate")

    print(f"  [AI] final: {len(collected)}/{target_n}")
    return collected


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
async def fetch_all(
    topic: str,
    total: int = 30,
    pyq_n: int | None = None,
    bank_n: int | None = None,
    ai_n: int | None = None,
) -> list[Question]:
    """
    Fetch questions from all three sources and return a numbered, deduped list.
    Default split: 33/33/34 (pyq/bank/ai).
    """
    third = total // 3
    pyq_n = pyq_n if pyq_n is not None else third
    bank_n = bank_n if bank_n is not None else third
    ai_n = ai_n if ai_n is not None else (total - pyq_n - bank_n)

    all_qs: list[Question] = []

    # Source 1: PYQs — target testbook's question-answer pages and theexampillar PYQ pages
    pyqs = await _scrape_source(
        topic, "question answer UKSSSC Patwari Lekhpal solved",
        "pyq", pyq_n, all_qs,
        extra_queries=[
            f"site:theexampillar.com {topic} UKSSSC questions",
            f"site:kafaltree.com {topic} MCQ questions answers",
        ],
    )
    all_qs.extend(pyqs)

    # Source 2: Question banks — broad topic MCQ pages
    banks = await _scrape_source(
        topic, "MCQ practice questions answers",
        "bank", bank_n, all_qs,
        extra_queries=[
            f"site:studyfry.com {topic} questions",
        ],
    )
    all_qs.extend(banks)

    # Source 3: AI-generated
    ai_qs = await _generate_ai_questions(topic, ai_n, all_qs)
    all_qs.extend(ai_qs)

    # Renumber sequentially
    for i, q in enumerate(all_qs, 1):
        q.n = i

    print(f"\n=== TOTAL: {len(all_qs)} questions "
          f"(pyq={len(pyqs)}, bank={len(banks)}, ai={len(ai_qs)}) ===")
    return all_qs


def build_paper_json(topic: str, questions: list[Question], path: Path) -> None:
    """Write questions to a paper JSON compatible with build_paper.py."""
    slug = re.sub(r"[^\w]", "-", topic.lower())[:40]
    data = {
        "filename": f"{slug}.docx",
        "ppt_filename": f"{slug}.pptx",
        "solution_filename": f"{slug}-solution.docx",
        "answer_key_filename": f"{slug}-answer-key.docx",
        "title_latin": topic,
        "title_hindi": topic,
        "subtitle_hindi": "अभ्यास प्रश्नपत्र",
        "solution_title": f"{topic} — हल",
        "solution_subtitle": "विस्तृत उत्तर",
        "answer_key_title": f"{topic} — उत्तरमाला",
        "questions": [q.to_dict() for q in questions],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Written: {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse
    p = argparse.ArgumentParser(description="Fetch questions for a topic")
    p.add_argument("topic", help="Topic in Hindi or English, e.g. 'पंवार वंश'")
    p.add_argument("--total", type=int, default=30)
    p.add_argument("--pyq-n", type=int, default=None)
    p.add_argument("--bank-n", type=int, default=None)
    p.add_argument("--ai-n", type=int, default=None)
    p.add_argument("--out", type=str, default=None)
    p.add_argument("--dry", action="store_true", help="Plan only, no API calls")
    args = p.parse_args()

    if args.dry:
        third = args.total // 3
        pyq_n = args.pyq_n or third
        bank_n = args.bank_n or third
        ai_n = args.ai_n or (args.total - pyq_n - bank_n)
        print(f"DRY PLAN — topic: {args.topic}")
        print(f"  Source 1 PYQ:   {pyq_n} questions via search+scrape")
        print(f"  Source 2 Bank:  {bank_n} questions via search+scrape")
        print(f"  Source 3 AI:    {ai_n} questions via Claude+corpus+verify")
        print(f"  Total target:   {args.total}")
        print(f"  Output:         {args.out or 'review/<topic>.json'}")
        return

    out_path = Path(args.out) if args.out else (
        BASE / "review" / f"{re.sub(r'[^\\w]', '-', args.topic)[:40]}.json"
    )

    async def run():
        qs = await fetch_all(
            args.topic,
            total=args.total,
            pyq_n=args.pyq_n,
            bank_n=args.bank_n,
            ai_n=args.ai_n,
        )
        build_paper_json(args.topic, qs, out_path)

    asyncio.run(run())


if __name__ == "__main__":
    main()
