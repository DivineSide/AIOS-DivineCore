# -*- coding: utf-8 -*-
"""AI-generative question pipeline — subject + count -> N exam-grade questions.

REDESIGNED 2026-07-12 as a HARNESS (same philosophy that fixed extraction):
the model supplies knowledge, code builds structure, mechanical gates detect
failure, and an informed retry loop corrects it. Modules:

  blueprint.py     — the harness owns every count (format slots per paper,
                     subjects per exam) via largest-remainder allocation of
                     MEASURED distributions from real papers. No prose quotas.
  formats.py       — per-format contracts. For सुमेलित/कथन/A-R/क्रम the model
                     returns only facts (pairs, statements, order, relation);
                     code assembles the stem block, options and answer letter,
                     so structural inconsistency is impossible.
  validate_gen.py  — pure-code invariants (options, Hindi, year sanity) +
                     paper-level guards (stem dedup, entity-repeat).
  ground.py        — Haiku grounding gate: the claimed fact must be quotable
                     from the source passages, else the question is rejected.

Per-slot flow (ONE topic, ONE format, its own context — variety by structure):

    passages = passage_lookup(topic, subject)          # substance (multi-fact)
    examples = pyq_rag_lookup(topic, subject, format)  # style, format-true
    draft    = GEN_MODEL(contract, passages, examples) # knowledge only
    q        = formats.build(draft)                    # code assembles
    validate -> paper-guard -> ground                  # mechanical gates
    failure  -> retry with the SPECIFIC reason fed back (<=2), else drop the
                slot and top up from another topic. Deliverable stays clean;
                drops are reported in gen-meta for the dashboard.

Modes:
    generate_questions(subject, count) -> (questions, meta)   # Phase A (live)
    generate_exam(exam, total)         -> (questions, meta)   # Phase B —
        per-exam quotas get locked WITH THE CLIENT; blueprint's measured
        SUBJECT_MIX is the opening proposal.

Topic sourcing differs by mode (2026-07-18, syllabus.py):
    subject mode — no exam context exists, so topics are inferred from a
        random PYQ sample (what the exam family actually tests, in aggregate).
    exam mode    — the OFFICIAL syllabus (syllabus.py, transcribed from the
        commission's advertisement PDFs) seeds the topics; PYQs then only
        supply per-topic style examples. A syllabus topic with zero PYQ
        coverage still generates (style prompt degrades gracefully) — this is
        how a fresh syllabus revision gets covered before any past paper
        tests it, and it decouples topic VARIETY from PYQ-pool size.
"""
import asyncio
import logging
import os
import sys
import threading
import time
import zlib
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[2]
RAG = REPO_ROOT / "clients" / "target-academy" / "rag"
# Our own folder too: Celery imports this as worker.generate (package mode), so
# `import blueprint` needs worker/ on sys.path explicitly — running generate.py
# as a script from its own directory hides this, package mode does not.
WORKER_DIR = Path(__file__).resolve().parent
for _p in (str(WORKER_DIR), str(RAG)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import query as rag  # noqa: E402
import sample as rag_sample  # noqa: E402

import batch_gen  # noqa: E402
import blueprint  # noqa: E402
import formats  # noqa: E402
from validate_gen import PaperGuard, validate_question  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
# Drafting is the intelligence step — worth the smart tier. Output is small
# (facts only, code builds the rest), so cost stays ~$1 per 100-question paper.
GEN_MODEL = os.environ.get("GEN_MODEL", SONNET)

GEN_PROVIDER = os.environ.get("GEN_PROVIDER", "anthropic").lower()
# Tried sarvam-30b (2026-07-22): ~9x faster per raw draft call than 105b, but
# a real 50Q pipeline test showed it ignores SLOT_SYSTEM's "never reference
# the study material in the reason text" rule far more often than 105b does
# (~86% of all drops were this one instruction-following miss, not real
# grounding failures) — the retry churn from that made the NET paper slower
# than 105b despite the faster raw calls (32/50 questions in 26.9 min).
# Reverted to 105b; reasoning_effort stays disabled below regardless of
# model (see _sarvam_reasoning_effort) since that part of the speedup is
# real and doesn't carry this tradeoff. Revisit 30b if the prompt gets
# tightened enough to close the instruction-following gap.
SARVAM_MODEL = os.environ.get("SARVAM_MODEL", "sarvam-105b")
SARVAM_BASE_URL = "https://api.sarvam.ai/v1"

# GEN_PROVIDER=groq — free-tier drafting on Groq's open-weight lineup, added
# 2026-08-24 when Sarvam's ~7x price hike (2026-08-05) + a zero-balance key
# made Sarvam unusable with no budget. gpt-oss-120b (Apache 2.0, MoE 117B
# total / 5.1B active) is the pick: OpenAI's model card reports MMMLU Hindi
# 82.2, and an independent Hindi benchmark (arXiv 2508.19831) puts it top of
# >20B models on IFEval-Hi — the "follows instructions in Hindi" axis, which
# is exactly what killed sarvam-30b here (86% of drops were one broken
# instruction, not a knowledge gap). See rag/RAG_ROADMAP.md §8 for the full
# decision + the paid candidates parked for later.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# gpt-oss exposes reasoning_effort as a real API param (low/medium/high,
# default medium). We pin "low": this task is one short factual MCQ as JSON —
# same reasoning as _sarvam_reasoning_effort's docstring, no multi-step
# thinking needed, and reasoning tokens are pure latency+quota cost on a free
# tier. This is ALSO the specific failure we live-tested on qwen3.6-27b
# (2026-08-24): it burned its entire token budget on English chain-of-thought
# and never emitted the Hindi answer. gpt-oss lets us dial that off.
GROQ_REASONING_EFFORT = os.environ.get("GROQ_REASONING_EFFORT", "low")

TOPICS_DIVISOR = 2       # ~count/2 distinct topics (was 4 — variety collapsed)
TOPICS_CAP = 40
PYQ_SEED_K = 40          # random PYQs fed to topic extraction
BOOK_TOP_K = 4           # passages per slot
PYQ_TOP_K = 2            # style examples per slot
PASSAGE_THRESHOLD = 0.20
PYQ_THRESHOLD = 0.10

TOPIC_DEDUP_THRESHOLD = 0.78   # cosine sim above this = treat as duplicate
                               # enough to refetch. MEASURED, not guessed
                               # (2026-07-25): real same-fact rephrasings
                               # ("गढ़वाली बोली की उत्पत्ति" vs "...किस भाषा का
                               # रूप") score 0.81 and 0.80; a genuinely
                               # DIFFERENT topic in the same domain ("पंवार
                               # वंश के शासक" vs "चंद वंश के शासक" — two
                               # different dynasties) scores 0.73 — these
                               # ranges OVERLAP, so no threshold perfectly
                               # separates "same fact reworded" from
                               # "related but distinct fact" on short topic
                               # phrases with this embedding model. Goal is
                               # NOT zero topic overlap (real exams legitimately
                               # cluster several questions per broad theme) —
                               # it's minimizing exact-same-fact collisions.
                               # A false-positive refetch just produces
                               # another valid topic (cheap); a false
                               # negative reproduces today's Q77/Q82-style
                               # contradiction (expensive) — asymmetric cost
                               # justifies erring aggressive over conservative.
TOPIC_DEDUP_MAX_REFETCH = 3    # refetch attempts per colliding topic before
                               # accepting the closest candidate and moving on

AR_EXPLAIN_THRESHOLD = 0.75    # cosine sim above this = R just restates A,
                               # not a genuine explanation. formats.py's
                               # build_assertion() already hard-rejects
                               # BYTE-IDENTICAL A/R (2026-07-24 Q76 bug), but
                               # a live paper (2026-07-26, Q86) shipped a
                               # PARAPHRASE-level restatement instead: A =
                               # "केदारनाथ...चार धामों में से एक धाम है", R =
                               # "केदारनाथ...चार धामों में से एक धाम है" reworded
                               # — same claim, not an explanation of WHY it's
                               # true. MEASURED (2026-07-26, OpenAI embeddings):
                               # that real bug pair scores 0.82; genuinely
                               # distinct A/R pairs (independent causal reason,
                               # not a reworded claim) score 0.35-0.37; a
                               # borderline near-restatement scores 0.63 — clean
                               # separation with margin on both sides at 0.75.

MAX_SLOT_ATTEMPTS = 3    # 1 draft + up to 2 informed retries per slot
IN_FORMAT_TOPUP_RETRIES = 2   # a dropped rare-format slot gets this many
                              # top-up attempts in its OWN format before
                              # falling back to plain (see generate_questions'
                              # top-up loop) — counts against the topup
                              # circuit-breaker same as any other attempt,
                              # just doesn't give up on the pre-planned
                              # format immediately
# The paper's requested count is a PROMISE, not a target: a grounding
# rejection is a legitimate reason to drop ONE question, never a reason to
# under-deliver the PAPER. MAX_TOPUP used to be a flat 8 regardless of paper
# size — fine for a 10-question test, but mathematically guaranteed to fall
# short on a 100-question paper the moment more than 8 slots failed (observed
# live: job dd0ccd49fa354c3f, 44 real drops, delivered 81/100 because topup's
# budget ran out at 8, not because the harness couldn't recover more with
# fresh topics/passages). Fix: topup now keeps retrying — new topic, fresh
# RAG context each attempt — until the paper reaches its exact requested
# count. TOPUP_CIRCUIT_BREAKER exists ONLY to stop a truly pathological case
# (e.g. a subject with zero usable passages at all, where no number of
# retries could ever succeed) from looping forever; it's sized as a large
# multiple of the paper's own count so it should never trigger in practice —
# if it does, that's a real corpus/retrieval problem worth surfacing, not
# something to silently paper over by shipping short.
TOPUP_CIRCUIT_BREAKER_MULTIPLE = 5   # give up only after 5x the paper's own
                                     # question count in topup attempts
# Slots are independent network-bound work; only the PaperGuard is
# cross-question. Waves of K slots run fully parallel, then commit through the
# guard sequentially at the wave boundary — a collision (two slots landing the
# same answer entity) fails the later one, which re-runs next wave WITH the
# collision reason (informed, not blind). K=6 ≈ 6x wall-clock with zero gate
# skipped; above ~8 you brush API rate limits for marginal gain.
GEN_CONCURRENCY = max(1, int(os.environ.get("GEN_CONCURRENCY", "6")))

VALID_ANSWERS = {"a", "b", "c", "d"}

SUBJECT_LABELS = {
    "uk-history":          "उत्तराखंड का इतिहास",
    "uk-geography":        "उत्तराखंड का भूगोल",
    "uk-culture":          "उत्तराखंड की संस्कृति",
    "uk-general-studies":  "उत्तराखंड सामान्य अध्ययन",
    "general-gk":          "सामान्य ज्ञान",
    "hindi":               "सामान्य हिंदी",
    "computer":            "कंप्यूटर",
}

# Per-slot system prompt. Lean by design: the format CONTRACT carries the
# structural rules, the passages carry the facts, the examples carry the style
# — prose only states what code cannot enforce.
# SLOT_SYSTEM and _RETRY_USER (the older, prohibition-heavy prompt) went to
# .archive/dsideos-slot-engine/ with the engine that used them. The live
# prompt is batch_gen.BATCH_SYSTEM, rewritten as a construction method.

# ── Groq drafting pool (free tier) ───────────────────────────────────────────
# Same key-pool + token-bucket + rotate-on-429 shape as rag/build_passages.py's
# _groq_pool/_TokenBucket — that pattern was tuned against real Groq free-tier
# behaviour (see its comments: a blind inter-request sleep does NOT survive
# concurrency, because N workers all spend the SAME key's budget at once).
# Reused here rather than reinvented, but with gpt-oss-120b's own, TIGHTER
# ceiling: 8,000 TPM / 200,000 TPD per key (vs the 12K TPM that file assumes
# for llama-3.3-70b). GEN_CONCURRENCY defaults to 6, so without a real budget
# gate a 100Q paper would thrash into 429s immediately.
_GROQ_KEY_ENVS = ["GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY_4"]
_GROQ_TPM_BUDGET = 7_200          # margin under the real 8,000 TPM cap
_GROQ_TPM_WINDOW_S = 60.0
# One draft call's worst case: SLOT_SYSTEM + 4 passages + 2 PYQ examples in,
# up to 1500 out. Passages dominate; measured slot prompts land ~2-3K tokens.
_GROQ_MAX_TOKENS_PER_CALL = 1500 + 3000
GROQ_MAX_RATE_LIMIT_RETRIES = 4   # per key, before falling through to the next
GROQ_RETRY_BACKOFF_BASE_S = 2.0   # 2s, 4s, 8s, 16s

_groq_clients: list | None = None
_groq_buckets: list | None = None


class _GroqTokenBucket:
    """Thread-safe sliding-window token budget for ONE Groq key. _draft is
    called via asyncio.to_thread from several concurrent slots, so this must
    be thread-safe, not just coroutine-safe."""

    def __init__(self, budget: int, window_s: float):
        self.budget = budget
        self.window_s = window_s
        self._lock = threading.Lock()
        self._usage: list[tuple[float, int]] = []

    def acquire(self, tokens: int) -> None:
        """Block until `tokens` of budget is free in the sliding window.

        Raises if a single request exceeds the whole budget: that can NEVER be
        satisfied, so the old unconditional loop hung forever with no error
        (hit live 2026-09-11 — a 10-section batch needed ~20k tokens against a
        7.2k/min budget and the process just stopped). Failing loudly turns an
        invisible deadlock into a caller-visible error it can act on.
        """
        if tokens > self.budget:
            raise RuntimeError(
                f"request needs {tokens} tokens but the per-key budget is "
                f"{self.budget}/min — split the batch or raise the tier")
        while True:
            with self._lock:
                now = time.time()
                cutoff = now - self.window_s
                self._usage = [(t, n) for t, n in self._usage if t > cutoff]
                used = sum(n for _, n in self._usage)
                if used + tokens <= self.budget:
                    self._usage.append((now, tokens))
                    return
                wait = self.window_s - (now - self._usage[0][0]) + 0.1
            time.sleep(max(wait, 0.1))


def _groq_pool() -> list:
    global _groq_clients
    if _groq_clients is None:
        from openai import OpenAI
        keys = [os.environ[k] for k in _GROQ_KEY_ENVS if os.environ.get(k)]
        if not keys:
            raise RuntimeError("No GROQ_API_KEY set (required for GEN_PROVIDER=groq).")
        _groq_clients = [OpenAI(api_key=k, base_url=GROQ_BASE_URL,
                                timeout=90, max_retries=2) for k in keys]
        logger.info("groq drafting pool: %d key(s), model=%s effort=%s",
                    len(_groq_clients), GROQ_MODEL, GROQ_REASONING_EFFORT)
    return _groq_clients


def _groq_bucket_pool() -> list:
    global _groq_buckets
    if _groq_buckets is None:
        _groq_buckets = [_GroqTokenBucket(_GROQ_TPM_BUDGET, _GROQ_TPM_WINDOW_S)
                         for _ in _groq_pool()]
    return _groq_buckets


def _is_groq_rate_error(exc: Exception) -> bool:
    msg = f"{type(exc).__name__} {exc}".lower()
    return any(s in msg for s in ("429", "rate_limit", "ratelimit", "quota",
                                  "too many requests"))


def _draft_groq(system: str, messages: list[dict]) -> str:
    """Draft on Groq's free tier. Budget-gated per key, rotating to the next
    key's independent quota on a 429 that slips past the bucket (server-side
    accounting is stricter than our estimate, and a DAILY-quota exhaustion is
    invisible to a 60s bucket). Raises the last error only once every key is
    exhausted — _gen_slot_inner already treats a draft exception as a slot
    failure with a reason, so the paper degrades rather than dying."""
    pool = _groq_pool()
    buckets = _groq_bucket_pool()
    last_err: Exception | None = None
    for client, bucket in zip(pool, buckets):
        for attempt in range(GROQ_MAX_RATE_LIMIT_RETRIES):
            bucket.acquire(_GROQ_MAX_TOKENS_PER_CALL)
            try:
                resp = client.chat.completions.create(
                    model=GROQ_MODEL, max_tokens=1500,
                    reasoning_effort=GROQ_REASONING_EFFORT,
                    messages=[{"role": "system", "content": system}] + messages,
                )
                choice = resp.choices[0]
                out = (choice.message.content or "").strip()
                if not out:
                    # Same canary as _draft_sarvam: an empty body with a
                    # non-stop finish_reason means the budget went somewhere
                    # other than content (reasoning, or a hard cap).
                    logger.warning("GROQ empty content (finish=%s, completion_toks=%s)",
                                   choice.finish_reason,
                                   getattr(resp.usage, "completion_tokens", "?"))
                return out
            except Exception as e:
                last_err = e
                if not _is_groq_rate_error(e):
                    raise
                sleep_s = GROQ_RETRY_BACKOFF_BASE_S * (2 ** attempt)
                logger.warning("GROQ 429 (attempt %d/%d) — backoff %.0fs",
                               attempt + 1, GROQ_MAX_RATE_LIMIT_RETRIES, sleep_s)
                time.sleep(sleep_s)
    raise last_err or RuntimeError("all Groq keys exhausted")


# ── model calls ──────────────────────────────────────────────────────────────

def _draft_structured(system: str, user: str, response_format: dict) -> str:
    """Draft with CONSTRAINED DECODING — the schema is enforced by the sampler,
    not by prompt adherence, so a wrong-shaped reply is impossible rather than
    something we detect and retry (see batch_gen's docstring).

    Groq only: gpt-oss-120b supports `strict: true` (verified live 2026-09-06).
    Sarvam/Anthropic have no equivalent here, so this raises rather than
    silently degrading to unconstrained output — a silent fallback would
    reintroduce exactly the parse failures the schema exists to eliminate.

    Error handling: rate-limit retries and key rotation are inherited from
    _draft_groq's pool/bucket; anything else propagates to the caller, which
    turns it into one drop per section.
    """
    if GEN_PROVIDER != "groq":
        raise RuntimeError(
            f"structured output requires GEN_PROVIDER=groq, got {GEN_PROVIDER!r}")
    pool, buckets = _groq_pool(), _groq_bucket_pool()
    # Reserve from the REAL prompt size — a batch prompt scales with section
    # count, so the fixed per-slot estimate under-reserves badly and the
    # server-side 429 lands before our own bucket notices. ~3 chars/token is
    # conservative for Devanagari (which tokenises worse than Latin).
    est_in = (len(system) + len(user)) // 3
    max_out = min(8000, max(1200, _GROQ_TPM_BUDGET - est_in - 500))
    need = est_in + max_out
    last: Exception | None = None
    for client, bucket in zip(pool, buckets):
        for attempt in range(GROQ_MAX_RATE_LIMIT_RETRIES):
            bucket.acquire(need)
            try:
                resp = client.chat.completions.create(
                    model=GROQ_MODEL, max_tokens=max_out,
                    reasoning_effort=GROQ_REASONING_EFFORT,
                    response_format=response_format,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as e:
                last = e
                if not _is_groq_rate_error(e):
                    raise
                time.sleep(GROQ_RETRY_BACKOFF_BASE_S * (2 ** attempt))
    raise last or RuntimeError("all Groq keys exhausted")


    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


# ── the per-question slot engine lived here (ARCHIVED 2026-09-12) ──────────
# _ar_explain_check / _dedupe_topics / _extract_topics / _slot_context /
# _gen_slot / _gen_slot_inner / generate_questions, plus SLOT_SYSTEM and the
# unstructured drafting helpers, moved to
#     .archive/dsideos-slot-engine/slot_engine.py
# Superseded by batch_gen.py + generate_questions_batched(): 1 API call per
# question instead of ~4, deterministic variety via reuse tracking instead of
# probabilistic top-k, duplicates PREVENTED by cross-question awareness rather
# than detected and re-queued, and constrained decoding instead of prompt
# adherence + fence-stripping. See rag/RAG_ROADMAP.md §4.

def _seed(*parts) -> int:
    """Deterministic per-question shuffle seed.

    formats.build_* shuffles options with random.Random(seed); seeding from
    (subject, section, attempt) rather than the clock means the SAME question
    always lays its options out the same way — so a regenerated paper is
    diffable, and a bug is reproducible.
    """
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))


def _interleave_formats(questions: list[dict]) -> list[dict]:
    """Spread same-format questions apart in the finished paper.

    WHY: slots are built rare-formats-first then all `plain`
    (generate_questions builds `slots` that way so rare formats land on
    distinct early topics), and numbering is sequential — so every match /
    assertion / statement question clustered at the FRONT of the paper. Real
    papers interleave them.

    This is a PRESENTATION concern, deliberately decoupled from generation
    order: constraining batch composition to fix it would couple two unrelated
    things. Applied once, at the end, just before numbering.

    Greedy spacing: repeatedly take the format with the most questions left
    that is not the one just placed. O(n * k) for k formats (k=5), i.e. linear.
    Stable within a format, so a subject's questions keep their relative order.
    """
    if len(questions) < 3:
        return questions
    from collections import defaultdict
    buckets: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        buckets[q.get("format", "plain")].append(q)
    out: list[dict] = []
    last: str | None = None
    while any(buckets.values()):
        # most-remaining first, but never the format just placed (unless it is
        # the only one left — a single-format paper must still be emitted)
        cand = [f for f, qs in buckets.items() if qs and f != last]
        if not cand:
            cand = [f for f, qs in buckets.items() if qs]
        pick = max(cand, key=lambda f: len(buckets[f]))
        out.append(buckets[pick].pop(0))
        last = pick
    return out


# ── batched generation (round-2 rebuild, 2026-09-11) ─────────────────────────
# GEN_BATCHED=1 routes generation through ONE model call per subject instead of
# one per question. See worker/batch_gen.py for the prompt/schema and
# rag/RAG_ROADMAP.md §4 for why retrieval no longer embeds anything.
#
# The old per-slot path (_gen_slot) is kept for now as a fallback — batching is
# new and unproven on a full paper. Once a real 100Q run is clean, delete the
# slot engine rather than maintaining two prompt surfaces and two gate paths.
GEN_BATCHED = os.environ.get("GEN_BATCHED", "0") == "1"
# Top-up rounds for the batched path. Bounded (unlike the slot
# engine's uncapped loop) because each round costs a full model call
# per format — on a thin subject that spins without converging.
TOPUP_MAX_ROUNDS = max(0, int(os.environ.get("GEN_TOPUP_ROUNDS", "2")))


def _style_examples(subject: str, exam: str | None, conn,
                    k: int = 2) -> list[str]:
    """A few REAL past questions from this exam+subject, for register only.

    Subject-level, never topic-level (deliberate): a newly added syllabus topic
    would have no past questions, and per-topic examples drag generation toward
    the example's own niche. Sampled fresh each run so consecutive papers do not
    converge on one example's phrasing.

    Falls back exam-scoped -> subject-global, and returns [] rather than raising
    — style is a nice-to-have, not a precondition for generating.

    Complexity: 1 indexed query. O(k) rows returned.
    """
    try:
        with conn.cursor() as cur:
            if exam:
                cur.execute("""SELECT chunk_text FROM pyq_chunks
                               WHERE exam=%s AND subject=%s
                               ORDER BY RANDOM() LIMIT %s""", (exam, subject, k))
                rows = cur.fetchall()
                if rows:
                    return [r[0][:700] for r in rows]
            cur.execute("""SELECT chunk_text FROM pyq_chunks
                           WHERE subject=%s ORDER BY RANDOM() LIMIT %s""",
                        (subject, k))
            return [r[0][:700] for r in cur.fetchall()]
    except Exception as e:
        logger.warning("style examples unavailable for %s: %s", subject, e)
        return []

async def generate_questions_batched(subject: str, count: int,
                                     exam: str | None = None,
                                     fmt_counts: dict[str, int] | None = None,
                                     ) -> tuple[list[dict], dict]:
    """One model call for this subject's whole allocation.

    Interface — same (questions, meta) contract as generate_questions(), so
    callers and the Celery task are unchanged.

    Flow:
      sections = rag_sample.sections_for(subject, count)   # metadata + RANDOM()
      draft    = ONE batched call, strict json_schema, 1 question per section
      per question: formats.build -> validate -> guard -> ground
      mark_used + advance_generation                       # reuse bookkeeping

    What is NOT here, deliberately: no topic extraction (sections come from the
    corpus), no topic dedup embeddings (sections are distinct by construction),
    no HyDE, no per-slot retry loop. Those existed to fix problems this design
    does not have — see RAG_ROADMAP §4.

    Complexity: 1 LLM call + 1 grounding call per question + ~2 DB round trips
    per section. Versus the slot engine: ~4 API calls per question.
    Scale note: fine to ~40 sections per subject; beyond that split the batch
    (batch_gen.build_batch_prompt's docstring explains why).
    """
    import psycopg2  # local: only the batched path needs a raw connection
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=30)
    drops: list[dict] = []
    out: list[dict] = []
    try:
        sections = await asyncio.to_thread(rag_sample.sections_for,
                                           subject, count, conn)
        if not sections:
            logger.error("batch[%s]: no tagged sections — has tag_sections.py "
                        "been run for this subject?", subject)
            return [], {"subject": subject, "drops": [
                {"topic": subject, "format": "plain",
                 "reason": "no tagged sections for this subject"}]}

        label = SUBJECT_LABELS.get(subject, subject)

        # PLAN BEFORE RETRIEVING ANYTHING: how many questions of each format,
        # and of each difficulty. Both are pure arithmetic (no API, no DB) and
        # are paired independently — see blueprint.plan_questions for why
        # difficulty must NOT be derived from format.
        if fmt_counts is None:
            fmt_counts = blueprint.allocate(len(sections), blueprint.format_mix())
        plan = blueprint.plan_questions(len(sections), fmt_counts)
        by_format = blueprint.group_by_format(plan)
        logger.info("batch[%s]: plan formats=%s difficulties=%s", subject,
                    {f: len(d) for f, d in by_format.items()},
                    dict(Counter(q["difficulty"] for q in plan)))

        # Real past questions from this exam+subject, sampled fresh per run for
        # register only (see batch_gen's style-example note).
        style = await asyncio.to_thread(_style_examples, subject, exam, conn)

        # ONE CALL PER (format, chunk). Grouping by format is what lets each
        # batch carry a single strict schema — a schema cannot say "item 3 is a
        # match and item 4 is plain". Chunking within a format is the Groq
        # free-tier TPM ceiling (~7.2k/key/min): a batch prompt scales with
        # section count, so an unchunked 10-section call can never be served.
        max_per_call = max(1, int(os.environ.get("GEN_BATCH_MAX_SECTIONS", "6")))
        _SYS_TOKENS = len(batch_gen.BATCH_SYSTEM) // 3
        _OUT_RESERVE = 1200 + 260 * max_per_call      # ~260 tok per question
        budget_chars = max(1500,
                           (_GROQ_TPM_BUDGET - _SYS_TOKENS - _OUT_RESERVE - 400) * 3)

        drafts: list[tuple[dict, str]] = []      # (draft, format)
        pos = 0
        for fmt, difficulties in by_format.items():
            take = sections[pos: pos + len(difficulties)]
            pos += len(difficulties)
            if not take:
                continue
            chunks, cur, cur_chars, cur_diff = [], [], 0, []
            for sec, d in zip(take, difficulties):
                sec_chars = len(sec[0]) + sum(len(p.get("text", "")) for p in sec[1])
                if cur and (cur_chars + sec_chars > budget_chars
                            or len(cur) >= max_per_call):
                    chunks.append((cur, cur_diff))
                    cur, cur_chars, cur_diff = [], 0, []
                cur.append(sec); cur_diff.append(d); cur_chars += sec_chars
            if cur:
                chunks.append((cur, cur_diff))

            for ci, (chunk, cdiff) in enumerate(chunks, 1):
                system, user, rfmt = batch_gen.build_batch_prompt(
                    subject, label, chunk, difficulties=cdiff, fmt=fmt,
                    style_examples=style)
                try:
                    raw = await asyncio.to_thread(_draft_structured, system, user, rfmt)
                except Exception as e:
                    logger.warning("batch[%s] %s chunk %d/%d failed: %s",
                                   subject, fmt, ci, len(chunks), e)
                    drops += [{"topic": sec, "format": fmt, "difficulty": dd,
                               "reason": f"batch call failed: {e}"}
                              for (sec, _), dd in zip(chunk, cdiff)]
                    continue
                drafts += [(d, fmt) for d in batch_gen.parse_batch(raw, chunk, fmt=fmt)]

        logger.info("batch[%s]: %d sections -> %d drafts", subject,
                    len(sections), len(drafts))
        if not drafts:
            return [], {"subject": subject, "requested": count,
                        "delivered": 0, "drops": drops}


        guard = PaperGuard(total=count)
        for d, fmt in drafts:
            passages = d.pop("_passages")
            section = d.pop("_section")
            difficulty_tag = d.pop("difficulty", "")
            try:
                q = formats.build(fmt, d, seed=_seed(subject, section, 0, 0))
            except formats.FormatError as e:
                drops.append({"topic": section, "format": fmt,
                              "difficulty": difficulty_tag, "reason": str(e)})
                continue
            reason = validate_question(q) or guard.check(q) or ""
            if reason:
                drops.append({"topic": section, "format": fmt,
                              "difficulty": difficulty_tag, "reason": reason})
                continue
            q["difficulty"] = difficulty_tag
            # NO GROUNDING GATE on the batched path (removed 2026-09-12, by
            # decision). The batched prompt hands the model ONE section's
            # material per question and tells it to use only that, which is a
            # much tighter constraint than the old per-slot prompt had — and a
            # measured 10/10 run had zero grounding rejections, so the gate was
            # costing a call per question to reject almost nothing.
            #
            # KNOWN TRADEOFF, stated plainly: nothing now verifies that a
            # generated fact is TRUE. Constrained decoding guarantees shape,
            # validate_question guarantees form, PaperGuard guarantees
            # cross-question distinctness — none of them read for truth. A live
            # test produced schema-perfect JSON asserting N.D. Tiwari was
            # Uttarakhand's first CM (it was Nityanand Swami); that class of
            # error now ships. ground.py is untouched and the old slot engine
            # still calls it, so this is one line to re-enable.
            guard.commit(q)
            q["subject"] = subject
            out.append(q)

        # TOP-UP — refill drops on FRESH sections, preserving the difficulty
        # mix. Without this every drop is permanent, and the loss is not random:
        # a hard question reaches for a niche fact, which is exactly what trips
        # the material-reference and distinctness gates, so drops eat hard and
        # moderate questions preferentially and the delivered paper skews easy
        # (observed 2026-09-12: planned 5/3/2, delivered 5/2/1).
        #
        # Regenerating with the SAME (format, difficulty) as each drop keeps the
        # plan intact rather than just topping the count back up with whatever
        # is easiest to produce.
        rounds = 0
        while drops and len(out) < count and rounds < TOPUP_MAX_ROUNDS:
            rounds += 1
            want = drops[:count - len(out)]
            fresh = await asyncio.to_thread(rag_sample.sections_for,
                                            subject, len(want), conn)
            if not fresh:
                logger.warning("batch[%s] topup: no eligible sections left", subject)
                break
            recovered: list[dict] = []
            # group the retry by format, same reason as the main pass
            by_fmt: dict[str, list[tuple]] = {}
            for d, sec in zip(want, fresh):
                by_fmt.setdefault(d.get("format", "plain"), []).append(
                    (sec, d.get("difficulty", "moderate")))
            for rfmt_name, items in by_fmt.items():
                secs_r = [s for s, _ in items]
                diffs_r = [d for _, d in items]
                system, user, rfmt = batch_gen.build_batch_prompt(
                    subject, label, secs_r, difficulties=diffs_r,
                    fmt=rfmt_name, style_examples=style)
                try:
                    raw = await asyncio.to_thread(_draft_structured, system, user, rfmt)
                except Exception as e:
                    logger.warning("batch[%s] topup %s failed: %s",
                                   subject, rfmt_name, e)
                    continue
                for d in batch_gen.parse_batch(raw, secs_r, fmt=rfmt_name):
                    ps = d.pop("_passages"); sec_name = d.pop("_section")
                    dtag = d.pop("difficulty", "")
                    try:
                        q = formats.build(rfmt_name, d,
                                          seed=_seed(subject, sec_name, rounds, 0))
                    except formats.FormatError:
                        continue
                    if validate_question(q) or guard.check(q):
                        continue
                    q["difficulty"] = dtag
                    q["subject"] = subject
                    guard.commit(q)
                    out.append(q)
                    recovered.append(q)
                # mark the retry's passages used too — the model saw them
                seen_extra = [pp["id"] for _, ps_ in secs_r for pp in ps_]
                await asyncio.to_thread(rag_sample.mark_used, seen_extra, conn)
            # drop the ones we just retried regardless of outcome: retrying the
            # same (format, difficulty) forever on a thin subject would spin.
            drops = drops[len(want):]
            logger.info("batch[%s] topup round %d: recovered %d",
                        subject, rounds, len(recovered))


        # Bookkeeping: every passage the MODEL SAW is marked, including ones
        # whose question was dropped — re-showing them would reproduce the same
        # question, so a drop must not make a passage look unused.
        seen = [p["id"] for _, ps in sections for p in ps]
        await asyncio.to_thread(rag_sample.mark_used, seen, conn)
        await asyncio.to_thread(rag_sample.advance_generation, conn)
    finally:
        conn.close()

    for i, q in enumerate(out, 1):
        q["n"] = i
        q.pop("_claim", None)
    logger.info("batch[%s]: delivered %d/%d (%d drops)",
                subject, len(out), count, len(drops))
    return out, {"subject": subject, "requested": count,
                 "delivered": len(out), "drops": drops}


async def generate_exam(exam: str, total: int) -> tuple[list[dict], dict]:
    """Exam mode. Harness owns the counts (blueprint SUBJECT_MIX — measured
    opening proposal, client-lockable); the OFFICIAL syllabus owns the topic
    taxonomy (syllabus.py, per-subject seeding inside generate_questions).
    Per-exam SUBJECT_MIX numbers remain the client-session deliverable.

    Subjects run CONCURRENTLY, not one after another: each subject gets its
    own PaperGuard (created fresh inside generate_questions), so there is no
    shared state a race could corrupt — a sequential for-loop here was only
    ever adding wall-clock time, not correctness. Measured: a 10-question
    exam paper (7 subjects, ~1-3 questions each) took ~10 minutes serial;
    each subject barely used the wave concurrency inside generate_questions
    because 1-3 slots rarely fills a GEN_CONCURRENCY=6 wave anyway — the
    real waste was subjects waiting on each other, not slots within a
    subject waiting on each other.

    One semaphore is created HERE and shared across every subject's
    generate_questions() call, so the GEN_CONCURRENCY cap applies to the
    whole paper at once, not per-subject (see generate_questions'/_gen_slot's
    docstrings) — and because it's scoped to this single call (this function
    is exactly what each Celery task wraps in its own asyncio.run()), it can
    never survive into a later job's event loop.

    Format variety is ALSO pre-decided here, once, before any subject starts
    generating: blueprint.exam_format_plan() measures each subject's REAL
    historical format mix from pyq_chunks (not one ratio flattened across
    every subject — see blueprint.py's per-subject-format-planning section)
    and hands each subject's generate_questions() call its own fmt_counts.
    Uses rag._db() (query.py's thread-local psycopg2 connection, already
    timeout-bounded) via asyncio.to_thread since this is a sync DB call in
    an async function; any failure here is caught inside exam_format_plan
    itself and degrades to today's global-format_mix-per-subject behavior,
    so a planning-query hiccup never blocks the job.

    Topics are ALSO extracted here, once, for every subject BEFORE any
    generation slot starts, then run through ONE cross-subject dedup pass —
    _extract_topics/_dedupe_topics previously only ever compared topics
    WITHIN one subject's own call, so two subjects that legitimately share
    ground (e.g. uk-history and uk-culture both touching "नंदा देवी राजजात
    यात्रा") could each independently pick it with zero cross-check, shipping
    the same question twice under two different subjects (observed live,
    2026-07-26, Q78/Q83). Per-subject topic extraction still runs CONCURRENTLY
    (asyncio.gather below) for the same wall-clock reason subjects do — only
    the dedup PASS over the combined result is sequential, and it's cheap
    (re-embeds ~n_topics short strings total, not the corpus)."""
    per_subject = blueprint.allocate(total, blueprint.subject_mix(exam))

    if GEN_BATCHED:
        # One call per subject, subjects still concurrent. No topic extraction
        # or cross-subject topic dedup: sections come from the corpus and are
        # distinct by construction, so the machinery those passes existed for
        # (a 9-topic syllabus pool colliding across subjects) has no job here.
        subs = [(su, n) for su, n in per_subject.items() if n > 0]
        results = await asyncio.gather(*[
            generate_questions_batched(su, n, exam=exam) for su, n in subs
        ])
        out: list[dict] = []
        metas: dict[str, dict] = {}
        for (su, _), (qs, m) in zip(subs, results):
            out.extend(qs)
            metas[su] = m
        out = _interleave_formats(out)
        for i, q in enumerate(out, 1):
            q["n"] = i
        return out, {"exam": exam, "per_subject_plan": per_subject,
                     "batched": True, "subjects": metas}
    # No non-batched path any more: the slot engine is archived (see the
    # note above and .archive/dsideos-slot-engine/). GEN_BATCHED is kept as a
    # flag only so a caller that still sets it is not surprised by a silent
    # behaviour change — batching is now the ONLY path.
    raise RuntimeError(
        "GEN_BATCHED=0 is no longer supported — the per-question slot engine "
        "was archived 2026-09-12 to .archive/dsideos-slot-engine/. "
        "Unset GEN_BATCHED or set it to 1."
    )
