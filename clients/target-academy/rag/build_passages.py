# -*- coding: utf-8 -*-
"""
build_passages — merge book_chunks fragments into generation-grade passages.

WHY (2026-07-12): the ingest chunker split text on printed lines, leaving
book_chunks as one-fact fragments (median 94-500 chars) plus ~4,900 junk/header
rows. Question generation needs multi-fact passages. The expensive intelligence
(topic boundaries, document order) was already paid for at ingest — this script
just coarsens the granularity: merge consecutive chunks of the same book until
a target size, drop junk, re-embed, store in book_passages. Cost: embeddings
only (~$0.05 for the whole corpus).

book_chunks stays canonical; book_passages is derived and rebuildable any time.

Usage:
    python build_passages.py --all --wipe          # full rebuild (default books)
    python build_passages.py --book kumau_ka_ethihas
    python build_passages.py --all --wipe --include-damaged   # after re-OCR lands

By default the 3 digit-corrupted uk-history books are EXCLUDED (their year facts
are OCR-mangled: 1790 -> 4790; see corpus_health.py). They enter book_passages
after their Sarvam re-OCR replaces them in book_chunks.
"""

import argparse
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

BASE = Path(__file__).resolve().parents[1]

# Same embedding space as everything else in the DB. OpenRouter when a key is
# present (ingest.py's route), else the direct OpenAI key — identical vectors,
# the provider is just transport.
EMBED_BATCH = 64
DB_BATCH    = 50

# Merge tuning. A passage flushes once it crosses TARGET_CHARS; MAX_CHARS is a
# hard cap so one giant source chunk can't produce a bloated passage.
TARGET_CHARS = 800
MAX_CHARS    = 1600
# Junk floor: fragments shorter than this never contribute (page headers, stray
# titles). They are logged, not silently eaten.
MIN_CHUNK_CHARS = 30
# A text repeated more than this many times within one book is running-header
# noise ("उत्तराखंड का इततहास" x3), not content.
MAX_REPEATS = 2

# Promo/front-matter junk — found ranking #1 on the very first passage retrieval
# test (jardhari's copyright page + email + review plea merged into a "passage").
# A chunk containing any of these is publisher furniture, not study material.
import re
_PROMO = re.compile(
    r"@gmail\.com|@yahoo|youtube\.com|https?://|www\.|"
    r"copyright|all rights reserved|£|"
    r"हमारे\s+YouTube|जुड़ें\s+हमारे\s+साथ|निशुल्क\s+कोर्स|ननशुल्क",
    re.IGNORECASE)
# MCQ-dump sections (the jardhari books embed Topic-Wise MCQ lists: "Q19....
# A.… B.… C.… D.…"). Question dumps are the wrong SHAPE for factual substance —
# generation needs prose passages; style examples come from pyq_chunks.
_MCQ_Q = re.compile(r"Q\s*\d{1,3}\s*[.।]")
_MCQ_OPT = re.compile(r"(?:^|\s)[A-D]\s*[.)]\s*\S")
# Table-of-contents blocks: several "chapter 4-10 / 11-21" page ranges in one
# chunk. TOCs carry every chapter title, so they rank high on topic queries
# while containing zero facts (caught polluting the गोरखा retrieval test).
_TOC_RANGE = re.compile(r"\d{1,3}\s*[-–]\s*\d{1,3}")
_TOC_WORDS = re.compile(r"content\s+page|तिर्षय\s*सूची|विषय\s*सूची|अनुक्रम", re.IGNORECASE)
# Corrupted-year chunks: Tesseract reads a printed '1' as '4' or '7', producing
# impossible CE dates ("7370 ई०" = 1370, "(4625-4638)" = 1625-1638). A passage
# that TEACHES a wrong year is worse than a missing passage — the grounding
# gate would DEFEND the wrong year, since the source states it. BCE dates
# ("4000 ई० पू०") are real ancient-history facts and are exempt.
_BAD_YEAR = re.compile(r"\b[4-9][0-9]{3}\s*(?:में|तक|से|ई(?![.०]?\s*पू))")
_BAD_YEAR_RANGE = re.compile(r"\(\s*[0-9]{3,4}\s*[-–]\s*[4-9][0-9]{3}\s*\)")


def _is_junk_content(t: str) -> str | None:
    if _PROMO.search(t):
        return "promo"
    if _MCQ_Q.search(t) and len(_MCQ_OPT.findall(t)) >= 3:
        return "mcq_dump"
    if _TOC_WORDS.search(t) or len(_TOC_RANGE.findall(t)) >= 4:
        return "toc"
    if _BAD_YEAR.search(t) or _BAD_YEAR_RANGE.search(t):
        return "bad_year"
    return None


# ── AI-restructuring (2026-07-23) ───────────────────────────────────────────
# WHY: some subjects (hindi, computer) are dominated by source books shaped as
# rule/formula tables ("राज + कुमार = राजकुमार = तत्पुरुष") or MCQ-dumps whose
# _is_junk_content() mcq_dump check above doesn't catch (mangled option
# markers slip past the ">=3 options" threshold). Neither shape states a
# question's specific claimed fact as a standalone quotable sentence, so the
# grounding gate (DsideOS/worker/ground.py) — which requires a LITERAL quote —
# rejects a correct-but-unquotable generated question. Confirmed NOT an OCR
# problem (garble score ~0.00 on these books); it's pure content shape.
#
# Fix: an OPT-IN per-book pass (--restructure) that sends only the BAD-SHAPED
# passages (reuse the same heuristics below the MCQ-dump junk floor, plus a
# formula-density check) through an LLM that re-emits each as N standalone
# atomic factual sentences — one fact per output passage, maximally quotable.
# Clean prose passages (uk-history, uk-culture, etc. — already ground fine)
# are left completely untouched; this never runs on them.

# Formula/table shape: dense use of "=", "→", "+" — rule-table markers
# ("इ,ई + स्वर → य", "राज + कुमार = राजकुमार"). ">" was deliberately EXCLUDED
# (verified live: it's this corpus's markdown blockquote marker, "> ब्रजभाषा
# : ...", used throughout ordinary clean prose — including it flagged 130/614
# passages in one book, ALL false positives, zero of which were actually
# tables). >=4 of the remaining three symbols in one passage is a strong
# real table signal (plain prose rarely uses 4+ of them).
import re as _re
_FORMULA_CHARS = _re.compile(r"[=→+]")
FORMULA_DENSITY_MIN = 4

RESTRUCTURE_SUBJECTS = {"hindi", "computer"}  # scope per shape-scan this session;
                                              # general-gk deferred (grounds OK on
                                              # volume), uk-* already clean prose


def needs_restructuring(t: str) -> bool:
    """Per-PASSAGE shape check — only bad-shaped passages get restructured,
    clean prose in the same book passes through untouched (per-passage, not
    per-book, since even flagged books are a MIX of shapes)."""
    if _MCQ_Q.search(t) and len(_MCQ_OPT.findall(t)) >= 2:
        return True
    if len(_FORMULA_CHARS.findall(t)) >= FORMULA_DENSITY_MIN:
        return True
    return False


_RESTRUCTURE_MODEL = "llama-3.3-70b-versatile"
# Groq's free tier caps this model at ~100K tokens/DAY per org (confirmed
# live: one 212-passage book used ~98% of it) — a much tighter ceiling than
# the per-minute rate limit alone suggested. GROQ_API_KEY_2 (a second org/key)
# gives a second independent daily allowance; _groq_clients() builds a client
# per key found in env, and restructure_passage() rotates to the next key on
# a 429 (rate/quota) error instead of giving up — so a book bigger than one
# key's daily budget still gets covered by falling through to the next key,
# only degrading to "keep raw passage" once ALL configured keys are exhausted.
_GROQ_KEY_ENVS = ["GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY_4"]
_groq_clients: list[OpenAI] | None = None

# Groq's per-minute cap (12,000 TPM per key, confirmed live) is a REAL budget
# that a blind inter-request sleep doesn't respect under concurrency — 4
# workers each sleeping 0.15s still fire fast enough in aggregate to blow past
# 12K tokens in a minute (confirmed live: repeated 429s even WITH the sleep
# and 2-key fallback, because concurrent workers all hit the SAME key's
# budget at once). A real token-bucket, one per key, shared across all
# worker threads via a lock, makes every restructure_passage() call actually
# wait for real budget before firing — no more thrashing into the ceiling.
_TPM_BUDGET = 11_000        # stay a margin under Groq's 12,000 TPM cap
_TPM_WINDOW_SECONDS = 60.0
_MAX_TOKENS_PER_CALL = 1500 + 900   # max_tokens output + ~3000-char input / ~3.3 chars/token


class _TokenBucket:
    """Thread-safe sliding-window token budget for ONE Groq key."""
    def __init__(self, budget: int, window_s: float):
        self.budget = budget
        self.window_s = window_s
        self._lock = __import__("threading").Lock()
        self._usage: list[tuple[float, int]] = []   # (timestamp, tokens)

    def _prune(self, now: float):
        cutoff = now - self.window_s
        self._usage = [(t, n) for t, n in self._usage if t > cutoff]

    def acquire(self, tokens: int):
        """Block until `tokens` worth of budget is available in the window."""
        while True:
            with self._lock:
                now = time.time()
                self._prune(now)
                used = sum(n for _, n in self._usage)
                if used + tokens <= self.budget:
                    self._usage.append((now, tokens))
                    return
                # not enough room — sleep until the oldest usage ages out
                wait = self.window_s - (now - self._usage[0][0]) + 0.1
            time.sleep(max(wait, 0.1))


_groq_buckets: list["_TokenBucket"] | None = None


def _groq_pool() -> list[OpenAI]:
    global _groq_clients
    if _groq_clients is None:
        keys = [os.environ[k] for k in _GROQ_KEY_ENVS if os.environ.get(k)]
        if not keys:
            raise RuntimeError("No GROQ_API_KEY(_2) set (required for --restructure).")
        _groq_clients = [
            OpenAI(api_key=k, base_url="https://api.groq.com/openai/v1",
                  timeout=60, max_retries=2)
            for k in keys
        ]
    return _groq_clients


def _groq_bucket_pool() -> list["_TokenBucket"]:
    global _groq_buckets
    if _groq_buckets is None:
        _groq_buckets = [_TokenBucket(_TPM_BUDGET, _TPM_WINDOW_SECONDS)
                        for _ in _groq_pool()]
    return _groq_buckets


_RESTRUCTURE_SYSTEM = """You convert messy exam-prep source text into clean,
independently-verifiable factual sentences for a RAG corpus that grounds
generated exam questions.

The source text may be a rule/formula table (e.g. "राज + कुमार = राजकुमार =
तत्पुरुष") or a raw MCQ question-dump (numbered questions with options and an
answer key mixed together). Either way, your job is the same:

1. Find every discrete, checkable FACT the text actually states or an MCQ's
   answer key confirms.
2. Write EACH fact as ONE standalone declarative sentence with full context —
   no dangling pronouns, no "इनमें से", no references to "उपरोक्त" or "यह
   शब्द" without naming the actual word/concept.
3. Where a text states a general RULE with example instances, expand each
   named instance into its own concrete factual sentence (e.g. "राज + कुमार
   = राजकुमार = तत्पुरुष समास" -> "राजकुमार एक तत्पुरुष समास है, जिसका विग्रह
   'राजा का कुमार' है।"). Do not invent instances the text does not name.
4. If the input is an MCQ dump, extract the FACT the correct answer encodes
   (e.g. "27. कारक के कितने भेद हैं? ... उत्तर (b) 8" -> "हिंदी व्याकरण में
   कारक के 8 भेद होते हैं।"). DROP option letters, exam-source tags like
   '(रेलवे, 1997)', and raw answer-key notation — keep only the fact.
5. NEVER invent a fact that is not present in or directly derivable from the
   source. If a passage has no extractable fact, return an empty list.
6. Keep the SAME language as the input (Hindi stays Hindi, English stays
   English) and the same script.

Return ONLY this JSON, no prose, no fences:
{"facts": ["<standalone factual sentence 1>", "<standalone factual sentence 2>", ...]}"""


MAX_RATE_LIMIT_RETRIES = 4     # per key, before falling through to the next
RETRY_BACKOFF_BASE_S = 2.0     # 2s, 4s, 8s, 16s — incremental, not a fixed sleep


def restructure_passage(text: str) -> list[str]:
    """One passage -> N standalone atomic fact sentences via Groq.

    Two layers against Groq's free-tier limits: (1) each key has its own
    _TokenBucket (see _groq_bucket_pool) that blocks BEFORE sending a request
    once that key's real 60s token budget is spent — prevents most 429s
    outright, even under concurrency. (2) if a 429 still slips through
    (server-side accounting can be stricter than our estimate, or a daily-
    quota exhaustion the bucket can't know about), retry the SAME key up to
    MAX_RATE_LIMIT_RETRIES times with incremental backoff (2s, 4s, 8s, 16s)
    before moving to the next key's independent quota. Only after every key
    is exhausted does this give up and return [] — the caller keeps the RAW
    passage rather than losing content."""
    pool = _groq_pool()
    buckets = _groq_bucket_pool()
    last_err: Exception | None = None
    for client_idx, (client, bucket) in enumerate(zip(pool, buckets)):
        for attempt in range(MAX_RATE_LIMIT_RETRIES):
            bucket.acquire(_MAX_TOKENS_PER_CALL)
            try:
                resp = client.chat.completions.create(
                    model=_RESTRUCTURE_MODEL, max_tokens=1500, temperature=0,
                    messages=[{"role": "system", "content": _RESTRUCTURE_SYSTEM},
                              {"role": "user", "content": text[:3000]}],
                )
                raw = (resp.choices[0].message.content or "").strip()
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()
                data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
                facts = data.get("facts", [])
                return [f.strip() for f in facts if isinstance(f, str) and f.strip()]
            except Exception as e:
                last_err = e
                is_rate_limit = "429" in str(e) or "rate_limit" in str(e).lower()
                if is_rate_limit and attempt + 1 < MAX_RATE_LIMIT_RETRIES:
                    time.sleep(RETRY_BACKOFF_BASE_S * (2 ** attempt))
                    continue
                break   # non-rate-limit error, or retries exhausted on this key
        # this key is out of retries (or the error wasn't rate-limit-shaped) —
        # fall through to the next key's independent quota, if any
    print(f"    restructure error (keeping raw passage): {last_err}", flush=True)
    return []


def restructure_book(passages: list[dict], max_workers: int = 4) -> tuple[list[dict], dict]:
    """Fan out restructure_passage() over only the bad-shaped passages in this
    book's list; clean-shaped passages pass through unchanged. A passage whose
    restructuring fails or returns nothing also passes through unchanged (its
    raw text stays a candidate for grounding rather than being lost).

    Concurrency is modest (default 4); pacing against Groq's per-minute limit
    is handled by the per-key _TokenBucket inside restructure_passage() itself
    (blocks before sending once a key's real 60s budget is spent), not a
    blind inter-request sleep — confirmed live that a fixed sleep alone still
    let concurrent workers thrash into 429s."""
    stats = {"total": len(passages), "flagged": 0, "restructured_facts": 0,
             "kept_raw_after_attempt": 0, "skipped_clean": 0}
    flagged_idx = [i for i, p in enumerate(passages) if needs_restructuring(p["text"])]
    stats["flagged"] = len(flagged_idx)
    stats["skipped_clean"] = len(passages) - len(flagged_idx)
    if not flagged_idx:
        return passages, stats

    def _work(i):
        facts = restructure_passage(passages[i]["text"])
        return i, facts

    results: dict[int, list[str]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for i, facts in ex.map(_work, flagged_idx):
            results[i] = facts

    out: list[dict] = []
    for i, p in enumerate(passages):
        facts = results.get(i)
        if facts is None:              # never flagged -> pass through untouched
            out.append(p)
            continue
        if not facts:                  # flagged but restructuring failed/empty
            stats["kept_raw_after_attempt"] += 1
            out.append(p)
            continue
        stats["restructured_facts"] += len(facts)
        for fact in facts:
            out.append({
                "text": fact,
                "topic": p["topic"],
                "chunk_ids": p["chunk_ids"],
                "n_chunks": p["n_chunks"],
            })
    return out, stats

# Digit-corrupted books (Tesseract read printed '1' as '4'; ~600 chunks carry
# wrong years). Kept OUT of generation retrieval until their Sarvam re-OCR.
# BAHI302 graduated 2026-07-12: re-OCR'd via Sarvam (as "BAHI302.pdf"), 2/1338
# flagged chunks vs 239/1015 before.
# EMPTY since 2026-07-14: every digit-corrupted book has been Sarvam re-OCR'd
# and re-ingested (BAHI302 2026-07-12; ajay_rawat + उत्तराखंड का इतिहास
# 2026-07-14). Add a book here (DB book_name) to exclude it from passages if
# corpus_health ever flags fact-level damage again.
DAMAGED_BOOKS: set[str] = set()


def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return


_load_env()
_client: OpenAI | None = None
_EMBED_MODEL: str | None = None


def _oai() -> OpenAI:
    global _client, _EMBED_MODEL
    if _client is None:
        router_key = os.environ.get("OPENROUTER_API_KEY", "")
        if router_key:
            _client = OpenAI(api_key=router_key, base_url="https://openrouter.ai/api/v1",
                             timeout=90, max_retries=5)
            _EMBED_MODEL = "openai/text-embedding-3-small"
        else:
            _client = OpenAI(timeout=90, max_retries=5)  # direct OPENAI_API_KEY
            _EMBED_MODEL = "text-embedding-3-small"
    return _client


def _db():
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set in .env")
    return psycopg2.connect(url, connect_timeout=30)


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


# ── merge ────────────────────────────────────────────────────────────────────

def merge_book(rows: list[tuple]) -> tuple[list[dict], dict]:
    """rows: [(id, topic, text)] in document (id) order for ONE book.
    Returns (passages, stats). Pure code — no LLM."""
    from collections import Counter
    norm_counts = Counter(_norm(t) for _, _, t in rows)

    passages: list[dict] = []
    stats = {"junk_short": 0, "junk_repeat": 0, "junk_promo": 0,
             "junk_mcq": 0, "junk_toc": 0, "junk_bad_year": 0, "kept_chunks": 0}

    cur_texts: list[str] = []
    cur_topics: list[str] = []
    cur_ids: list[int] = []
    cur_len = 0

    def flush():
        nonlocal cur_texts, cur_topics, cur_ids, cur_len
        if cur_texts:
            seen, topics = set(), []
            for t in cur_topics:
                tn = t.strip()
                if tn and tn not in seen:
                    seen.add(tn)
                    topics.append(tn)
            passages.append({
                "text": "\n".join(cur_texts),
                "topic": " | ".join(topics[:6]),
                "chunk_ids": cur_ids,
                "n_chunks": len(cur_ids),
            })
        cur_texts, cur_topics, cur_ids, cur_len = [], [], [], 0

    for cid, topic, text in rows:
        t = text.strip()
        if len(t) < MIN_CHUNK_CHARS:
            stats["junk_short"] += 1
            continue
        if norm_counts[_norm(t)] > MAX_REPEATS:
            stats["junk_repeat"] += 1
            continue
        junk = _is_junk_content(t)
        if junk == "promo":
            stats["junk_promo"] += 1
            continue
        if junk == "mcq_dump":
            stats["junk_mcq"] += 1
            continue
        if junk == "toc":
            stats["junk_toc"] += 1
            continue
        if junk == "bad_year":
            stats["junk_bad_year"] += 1
            continue
        stats["kept_chunks"] += 1
        # a single huge chunk that would blow the cap flushes what came before
        if cur_len and cur_len + len(t) > MAX_CHARS:
            flush()
        cur_texts.append(t)
        cur_topics.append(topic or "")
        cur_ids.append(cid)
        cur_len += len(t)
        if cur_len >= TARGET_CHARS:
            flush()
    flush()
    return passages, stats


# ── embed + store ────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i: i + EMBED_BATCH]
        client = _oai()
        resp = client.embeddings.create(model=_EMBED_MODEL, input=batch)
        out.extend(r.embedding for r in resp.data)
        print(f"    embedded {min(i + EMBED_BATCH, len(texts))}/{len(texts)}", flush=True)
    return out


def store(passages: list[dict], book: str, subject: str):
    conn = _db()
    inserted = 0
    for i in range(0, len(passages), DB_BATCH):
        batch = passages[i: i + DB_BATCH]
        for attempt in range(2):
            try:
                with conn.cursor() as cur:
                    cur.executemany(
                        """INSERT INTO book_passages
                           (book_name, subject, topic, passage_text, n_chunks, chunk_ids, embedding)
                           VALUES (%s,%s,%s,%s,%s,%s,%s::vector)""",
                        [
                            (book, subject, p["topic"], p["text"], p["n_chunks"],
                             p["chunk_ids"],
                             "[" + ",".join(str(x) for x in p["embedding"]) + "]")
                            for p in batch
                        ],
                    )
                conn.commit()
                break
            except psycopg2.OperationalError as e:
                print(f"    batch at {inserted} failed ({e}) — reconnecting...", flush=True)
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _db()
                if attempt == 1:
                    raise
        inserted += len(batch)
    conn.close()
    print(f"    stored {inserted} passages")


# ── main ─────────────────────────────────────────────────────────────────────

def build(only_book: str | None, wipe: bool, include_damaged: bool,
         restructure: bool = False):
    conn = _db()
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT book_name, subject FROM book_chunks ORDER BY 1")
        books = cur.fetchall()
    conn.close()

    if only_book:
        books = [(b, s) for b, s in books if b == only_book]
        if not books:
            print(f"ERROR: book not found in book_chunks: {only_book}")
            sys.exit(1)

    skipped = [b for b, _ in books if b in DAMAGED_BOOKS and not include_damaged]
    if skipped:
        print(f"EXCLUDED (digit-corrupted, pending re-OCR): {skipped}")
        books = [(b, s) for b, s in books if b not in DAMAGED_BOOKS]

    if wipe:
        conn = _db()
        with conn.cursor() as cur:
            if only_book:
                cur.execute("DELETE FROM book_passages WHERE book_name = %s", (only_book,))
            else:
                cur.execute("TRUNCATE book_passages")
        conn.commit()
        conn.close()
        print("book_passages wiped." if not only_book else f"rows wiped for {only_book}.")

    grand = {"passages": 0, "junk_short": 0, "junk_repeat": 0,
             "junk_promo": 0, "junk_mcq": 0, "junk_toc": 0, "junk_bad_year": 0, "kept_chunks": 0}
    for book, subject in books:
        conn = _db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, topic, chunk_text FROM book_chunks WHERE book_name=%s ORDER BY id",
                (book,),
            )
            rows = cur.fetchall()
        conn.close()

        passages, stats = merge_book(rows)
        lens = [len(p["text"]) for p in passages] or [0]
        print(f"\n{book}  [{subject}]")
        print(f"  {len(rows)} chunks -> {len(passages)} passages "
              f"(avg {sum(lens)//len(lens)} chars) | junk dropped: "
              f"{stats['junk_short']} short + {stats['junk_repeat']} repeated-header "
              f"+ {stats['junk_promo']} promo + {stats['junk_mcq']} mcq-dump "
              f"+ {stats['junk_toc']} toc + {stats['junk_bad_year']} bad-year")

        if restructure and subject in RESTRUCTURE_SUBJECTS:
            passages, rstats = restructure_book(passages)
            print(f"  restructure: {rstats['flagged']}/{rstats['total']} passages "
                  f"flagged (bad shape) -> {rstats['restructured_facts']} atomic facts "
                  f"| {rstats['kept_raw_after_attempt']} kept raw (restructure failed) "
                  f"| {rstats['skipped_clean']} clean, untouched")

        embs = embed_texts([p["text"] for p in passages])
        for p, e in zip(passages, embs):
            p["embedding"] = e
        store(passages, book, subject)

        grand["passages"] += len(passages)
        for k in ("junk_short", "junk_repeat", "junk_promo", "junk_mcq",
                  "junk_toc", "junk_bad_year", "kept_chunks"):
            grand[k] += stats[k]

    dropped = (grand['junk_short'] + grand['junk_repeat'] + grand['junk_promo']
               + grand['junk_mcq'] + grand['junk_toc'] + grand['junk_bad_year'])
    print(f"\nDONE: {grand['passages']} passages from {grand['kept_chunks']} chunks "
          f"({dropped} junk chunks dropped: {grand['junk_short']} short, "
          f"{grand['junk_repeat']} header, {grand['junk_promo']} promo, "
          f"{grand['junk_mcq']} mcq-dump, {grand['junk_toc']} toc, {grand['junk_bad_year']} bad-year).")


# Same OCR-garble heuristic as query.py's _garble_score — duplicated rather
# than imported: query.py rewraps sys.stdout/stderr at import time (line
# 24-27), and importing it AFTER build_passages.py's own rewrap (line 34-35)
# double-wraps the same underlying buffer, which crashes with "I/O operation
# on closed file" once either wrapper gets garbage-collected. Keep both files'
# copies in sync if the regex ever changes.
_GARBLE_RX = re.compile(
    r"्[ा-ौॢॣ]"          # halant + vowel sign (impossible — halant only joins consonants)
    r"|््"                # double halant
    r"|[॒॑]"              # Vedic accent marks in exam prose
    r"|<[ऀ-ॿ]|[ऀ-ॿ]>"     # angle bracket wrapping Devanagari
    r"|(?:^|[\s(«»])[ा-ौ]"  # matra with no preceding consonant
)
_REPEAT_RX = re.compile(r"(.्)\1{3,}")   # same halant-joined char, 4+ times running


def _garble_score(text: str) -> float:
    text = text or ""
    if not text:
        return 0.0
    hits, pos = 0, 0
    while pos < len(text):
        m = _GARBLE_RX.search(text, pos)
        if not m:
            break
        hits += 1
        pos = m.start() + 1
    repeat_hits = sum(m.end() - m.start() for m in _REPEAT_RX.finditer(text))
    return 100.0 * (hits + repeat_hits) / len(text)


def inspect_books():
    """Standing pre-ingestion check: for every book already in book_chunks,
    classify it clean-prose vs needs-restructuring using the SAME deterministic
    heuristics the pipeline itself uses (MCQ-dump density, formula density,
    OCR-garble score) — so the plain-vs-AI-restructuring ingestion decision is
    data-driven, not a guess, for this book AND for any future book."""
    conn = _db()
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT book_name, subject FROM book_chunks ORDER BY 1")
        books = cur.fetchall()

    for book, subject in books:
        with conn.cursor() as cur:
            cur.execute("SELECT chunk_text FROM book_chunks WHERE book_name=%s "
                       "ORDER BY random() LIMIT 60", (book,))
            texts = [r[0] or "" for r in cur.fetchall()]
        n = len(texts) or 1
        mcq_n = sum(1 for t in texts if _MCQ_Q.search(t) and len(_MCQ_OPT.findall(t)) >= 2)
        formula_n = sum(1 for t in texts if len(_FORMULA_CHARS.findall(t)) >= FORMULA_DENSITY_MIN)
        garble_avg = sum(_garble_score(t) for t in texts) / n
        bad_shape_pct = 100 * (mcq_n + formula_n) / n
        verdict = ("NEEDS RE-OCR (garbled)" if garble_avg > 1.0 else
                  "NEEDS --restructure" if bad_shape_pct > 15 else
                  "clean — plain ingestion OK")
        print(f"{book:50.50} [{subject:20}] mcq={100*mcq_n/n:4.0f}% "
              f"formula={100*formula_n/n:4.0f}% garble={garble_avg:5.2f}  -> {verdict}")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Merge book_chunks into book_passages.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="all books")
    g.add_argument("--book", help="one book_name")
    g.add_argument("--inspect", action="store_true",
                   help="classify every book clean-prose vs needs-restructuring, no writes")
    ap.add_argument("--wipe", action="store_true", help="delete existing passages first")
    ap.add_argument("--include-damaged", action="store_true",
                    help="also build the digit-corrupted books (after their re-OCR)")
    ap.add_argument("--restructure", action="store_true",
                    help="AI-restructure bad-shaped passages (hindi/computer only, see "
                        "RESTRUCTURE_SUBJECTS) into standalone atomic facts before embedding")
    args = ap.parse_args()
    if args.inspect:
        inspect_books()
    else:
        build(args.book, args.wipe, args.include_damaged, args.restructure)
