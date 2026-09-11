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
import json
import logging
import os
import random
import sys
import threading
import time
import zlib
from pathlib import Path

logger = logging.getLogger(__name__)

import anthropic

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
import ground  # noqa: E402
import syllabus  # noqa: E402
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
SLOT_SYSTEM = """# ROLE
You are an Indian competitive-exam question writer (UKSSSC-style), writing in
Hindi (Devanagari). English proper nouns and technical terms stay in English.

# OBJECTIVE
Write ONE question of the format: {format_label} — topic: "{topic}" (subject:
{subject}) — whose correct answer is a fact EXPLICITLY STATED in the STUDY
MATERIAL below. Every question you write is checked by a separate grounding
model against that same material; a question whose answer is not literally in
the material is rejected and wasted. So your only path to success is a question
the material itself proves.

# THE ONE RULE THAT MATTERS
Build the question around a fact you can point to in the study material — a
specific sentence stating a name, place, year, work, scheme, or pairing.
- If the material clearly states such a fact: write the question on it.
- If the material only mentions the topic in passing, or you'd have to rely on
  your own knowledge to answer, DO NOT force a question. It is better to write
  a simpler question on a fact the material DOES state than to invent one it
  doesn't. Never supply a name/date/place from your own knowledge that is
  absent from the material — that is the single most common way questions fail.

# QUALITY RULES
- Distractors must be plausible: same category as the correct answer (a sibling
  dynasty, a neighbouring district, a similar organisation, a wrong year near
  the right one) — but the CORRECT option must be the material-supported one.
- Every distractor must be WRONG for this stem. Before finalising, test each
  distractor against the question: if it could also be a correct answer, the
  question is broken. (Asking "which is a प्रमुख विभाषा?" with four विभाषाएं
  as options fails this — when the stem asks membership of a set, distractors
  must come from OUTSIDE that set.)
- Prefer WHO/WHICH/WHAT (a person, place, organisation, book, scheme, term)
  over WHEN/HOW MANY — in real papers ~90% of answers are text, not numbers.
- Mirror the framing and register of the REAL PAST QUESTIONS shown.
- The student NEVER sees the study material — it exists only for you. The stem
  and the reason must therefore never refer to it: no "पाठ के अनुसार", no
  "प्रदत्त सामग्री के अनुसार", no "अध्ययन सामग्री में", no "स्रोत [N]". Ask the
  question as a standalone fact of the world, and write the reason as the bare
  fact in one sentence — "मेरठ की खड़ी बोली आदर्श और मानक मानी जाती है।" is
  right; "सामग्री के अनुसार, ..." is wrong. The same ban covers IMPLICIT
  references: a stem like "X के साथ उल्लेखित है" or "सूची में सम्मिलित है"
  depends on how the material happens to group things — if the question only
  makes sense relative to a text the student cannot see, it is broken.

# OUTPUT
Return ONLY this JSON object (no prose, no fences):
{contract}

━━━ REAL PAST QUESTIONS (style reference only — NOT a source of facts) ━━━
{examples}

━━━ STUDY MATERIAL (your ONLY source of facts) ━━━
{passages}

━━━ FINAL CHECK before you answer ━━━
Point to the sentence in the STUDY MATERIAL above that makes your correct
option correct. If no sentence states it, choose a different fact from the
material — do NOT fall back on your own knowledge."""

_RETRY_USER = """Your previous attempt was rejected. Problem: {reason}

Write a corrected question now — same topic, same format, same JSON shape.
Fix the specific problem; use ONLY facts from the study material."""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


_sarvam = None


def _sarvam_client():
    global _sarvam
    if _sarvam is None:
        from openai import OpenAI
        key = os.environ.get("SARVAM_API_KEY", "")
        if not key:
            raise RuntimeError("SARVAM_API_KEY not set (required for GEN_PROVIDER=sarvam).")
        _sarvam = OpenAI(base_url=SARVAM_BASE_URL, api_key=key)
    return _sarvam


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

def _draft_anthropic(system: str, messages: list[dict]) -> str:
    msg = _client().messages.create(
        model=GEN_MODEL,
        max_tokens=1500,
        system=[{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    u = msg.usage
    logger.info("DRAFT model=%s | in=%d cache_r=%d cache_w=%d out=%d",
                GEN_MODEL, u.input_tokens,
                getattr(u, "cache_read_input_tokens", 0) or 0,
                getattr(u, "cache_creation_input_tokens", 0) or 0,
                u.output_tokens)
    return msg.content[0].text.strip() if msg.content else ""


def _sarvam_reasoning_effort() -> str | None:
    """None fully disables sarvam's hidden reasoning phase (Sarvam's own docs:
    "use None to completely disable reasoning when you want the fastest
    possible responses" — a distinct, lower state than the string "low", not
    just the bottom of the low/medium/high enum). This task (one short MCQ,
    facts-only, structural JSON) has no need for multi-step reasoning — the
    "thinking" was pure overhead, and per Sarvam's docs a too-small token
    budget for reasoning is exactly what caused the empty-content bug below,
    not a fluke of this codebase. SARVAM_REASONING env can still force a
    level ("low"/"medium"/"high") for comparison, but the default is now off.
    NOTE: must be Python None / JSON null, not the string "none" — Sarvam's
    API expects the enum values or a null, not a fourth string value."""
    val = os.environ.get("SARVAM_REASONING", "").strip().lower()
    return val if val in ("low", "medium", "high") else None


def _draft_sarvam(system: str, messages: list[dict]) -> str:
    # max_tokens: starter tier hard-caps at 4096; run just under it. With
    # reasoning disabled (see _sarvam_reasoning_effort) the old "reasoning ate
    # the whole budget, content came back empty" failure mode shouldn't recur,
    # but the warning below stays as a canary in case it does.
    resp = _sarvam_client().chat.completions.create(
        model=SARVAM_MODEL, max_tokens=4000,
        extra_body={"reasoning_effort": _sarvam_reasoning_effort()},
        messages=[{"role": "system", "content": system}] + messages,
    )
    choice = resp.choices[0]
    out = (choice.message.content or "").strip()
    if not out:
        logger.warning("SARVAM empty content (finish=%s, completion_toks=%s)",
                       choice.finish_reason,
                       getattr(resp.usage, "completion_tokens", "?"))
    return out


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
    last: Exception | None = None
    for client, bucket in zip(pool, buckets):
        for attempt in range(GROQ_MAX_RATE_LIMIT_RETRIES):
            bucket.acquire(_GROQ_MAX_TOKENS_PER_CALL)
            try:
                resp = client.chat.completions.create(
                    model=GROQ_MODEL, max_tokens=8000,
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


def _draft(system: str, messages: list[dict]) -> str:
    if GEN_PROVIDER == "groq":
        return _draft_groq(system, messages)
    if GEN_PROVIDER == "sarvam":
        return _draft_sarvam(system, messages)
    return _draft_anthropic(system, messages)


def _complete(prompt: str, max_tokens: int = 1024) -> str:
    """Single-user-turn completion (no passages/system contract) for small
    helper tasks like topic extraction — routes through GEN_PROVIDER like
    _draft() does, instead of being hardcoded to one provider regardless of
    what's actually configured/funded. Previously _extract_topics() called
    anthropic.Anthropic() directly no matter what GEN_PROVIDER was set to;
    on a server with GEN_PROVIDER=sarvam and no ANTHROPIC_API_KEY (today's
    actual deployment), that call was GUARANTEED to fail every time it
    triggered — confirmed live via a real credit-exhaustion 400. Fails soft
    to "" on any error, same as before; callers already handle empty output
    by falling back to a subject-label topic."""
    if GEN_PROVIDER == "groq":
        # Routed through _draft_groq's budget gate + key rotation rather than a
        # bare client call: topic extraction fires per-subject at the START of
        # a paper, i.e. concurrently across 7 subjects in exam mode, and it
        # shares the SAME free-tier TPM budget as every draft call.
        return _draft_groq("You are a helpful assistant.",
                           [{"role": "user", "content": prompt}])
    if GEN_PROVIDER == "sarvam":
        resp = _sarvam_client().chat.completions.create(
            model=SARVAM_MODEL, max_tokens=max_tokens,
            extra_body={"reasoning_effort": _sarvam_reasoning_effort()},
            messages=[{"role": "user", "content": prompt}],
        )
        return (resp.choices[0].message.content or "").strip()
    msg = _client().messages.create(
        model=HAIKU, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip() if msg.content else ""


def _parse_json_object(text: str) -> dict | None:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        return None
    span = t[start:end + 1]
    for candidate in (span,
                      # models that echo template-escaped braces ({{...}}) —
                      # observed with sarvam-105b copying the contract literally
                      span.replace("{{", "{").replace("}}", "}")):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


# ── Phase 1 — subject -> topics ──────────────────────────────────────────────

def _parse_json_array(text: str) -> list:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip()
    start, end = t.find("["), t.rfind("]")
    if start != -1 and end > start:
        t = t[start:end + 1]
    try:
        data = json.loads(t)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def _ar_explain_check(q: dict) -> str:
    """Assertion-reason semantic gate — catches a PARAPHRASE-level restatement
    that formats.build_assertion()'s exact-match gate can't (byte-identical
    A/R is already hard-rejected there; this catches the softer case where R
    reworders A instead of explaining it, e.g. real Q86, 2026-07-26: A =
    "केदारनाथ...चार धामों में से एक धाम है", R = same claim reworded — not a
    cause/context for A, just A said twice). q['statements'] is always
    exactly [f"अभिकथन (A) : {assertion}", f"कारण (R) : {reason}"] per
    build_assertion — strip those fixed prefixes to get the raw claims back."""
    stmts = q.get("statements") or []
    if len(stmts) != 2:
        return ""
    a_txt = stmts[0].split(":", 1)[-1].strip()
    r_txt = stmts[1].split(":", 1)[-1].strip()
    a_emb, r_emb = await asyncio.gather(
        asyncio.to_thread(rag._embed, a_txt),
        asyncio.to_thread(rag._embed, r_txt),
    )
    if _cosine(a_emb, r_emb) >= AR_EXPLAIN_THRESHOLD:
        return ("assertion (A) and reason (R) are too semantically similar — "
                "R restates A's claim rather than explaining WHY it's true; "
                "write a genuine cause/context distinct from A's own wording")
    return ""


async def _dedupe_topics(topics: list[str], subject: str, exam: str | None,
                         official_pool: list[str],
                         seed_topics: list[str] | None = None,
                         seed_embeds: list[list[float]] | None = None,
                         ) -> list[str]:
    """Retrieval-first topic dedup: embed every topic BEFORE any generation
    slot is built, and replace any pair that's semantically the same
    underlying topic (not just a different string) — e.g. "गढ़वाली बोली की
    उत्पत्ति" and "गढ़वाली भाषा किस भाषा से" share zero substrings but ask the
    exact same fact. Keyword/stem comparison (what PaperGuard does post-hoc,
    on generated QUESTIONS) can't catch this; only embedding similarity on
    the TOPIC strings, done before generation starts, catches it up front —
    so two slots never even get assigned to write about the same fact,
    rather than catching it after two drafts already burned model calls.

    Official-syllabus topics get a replacement resampled from the unused
    remainder of the same official list (still authoritative, still
    official-only). LLM-inferred topics get re-prompted for one fresh
    replacement, explicitly excluding every topic already accepted.
    TOPIC_DEDUP_MAX_REFETCH caps retries per collision; if still colliding
    after that, the closest-to-unique candidate is accepted and logged
    loudly — this must never silently block or shrink the paper, same
    philosophy as the topup circuit breaker.

    `seed_topics`/`seed_embeds` (exam mode's cross-subject pass, see
    generate_exam): topics ALREADY CLAIMED BY OTHER SUBJECTS this paper,
    pre-embedded, so this subject's own topics get checked against them too
    — this function previously only ever compared topics WITHIN one
    subject's own call, so two subjects each independently landing on
    "नंदा देवी राजजात यात्रा" (a real culture/history crossover topic) never
    got compared against each other and both shipped as the same question
    (observed live, 2026-07-26, Q78/Q83). Seeding `accepted`/`accepted_embeds`
    reuses the exact same collision/refetch machinery below, just pre-primed
    with cross-subject claims instead of starting empty."""
    if len(topics) < 2 and not seed_topics:
        return topics

    embeds = await asyncio.gather(*[
        asyncio.to_thread(rag._embed, t) for t in topics
    ])
    accepted: list[str] = list(seed_topics or [])
    accepted_embeds: list[list[float]] = list(seed_embeds or [])
    n_seed = len(accepted)
    unused_official = [t for t in official_pool if t not in topics]

    for topic, emb in zip(topics, embeds):
        candidate, cand_emb = topic, emb
        for attempt in range(TOPIC_DEDUP_MAX_REFETCH + 1):
            sims = [_cosine(cand_emb, e) for e in accepted_embeds]
            worst = max(sims) if sims else 0.0
            if worst < TOPIC_DEDUP_THRESHOLD:
                break
            if attempt == TOPIC_DEDUP_MAX_REFETCH:
                logger.warning(
                    "topic-dedup[%s/%s]: '%s' still collides (sim=%.2f) after "
                    "%d refetches — accepting anyway, not blocking the paper",
                    subject, exam, candidate, worst, TOPIC_DEDUP_MAX_REFETCH)
                break
            if unused_official:
                candidate = unused_official.pop(random.randrange(len(unused_official)))
            else:
                exclude = ", ".join(f'"{t}"' for t in accepted + [candidate])
                prompt = (
                    f"Give ONE distinct exam topic/concept for the subject "
                    f"'{subject}', in Hindi (Devanagari). It must be "
                    f"COMPLETELY DIFFERENT from all of these already-used "
                    f"topics: {exclude}. Return ONLY the topic string, no "
                    f"prose, no JSON, no quotes."
                )
                try:
                    candidate = _complete(prompt, max_tokens=64).strip().strip('"')
                except Exception as e:
                    logger.warning("topic-dedup refetch failed (%s) — keeping "
                                   "prior candidate", e)
                    break
            if not candidate:
                break
            cand_emb = await asyncio.to_thread(rag._embed, candidate)
        accepted.append(candidate)
        accepted_embeds.append(cand_emb)
    return accepted[n_seed:]


async def _extract_topics(subject: str, count: int,
                          exam: str | None = None,
                          seed_topics: list[str] | None = None,
                          seed_embeds: list[list[float]] | None = None,
                          ) -> list[str]:
    """Derive distinct exam topics for `count` questions.

    Exam mode (exam on the master syllabus): the OFFICIAL taxonomy seeds the
    list — variety comes from the commission's own syllabus, not from
    whatever a 40-row PYQ sample happens to contain. Shortfall (official
    list smaller than n_topics) tops up from PYQ inference below.

    Subject mode (exam=None): PYQ-sample inference, unchanged — with no exam
    anchor there is no single official syllabus to consult.

    `seed_topics`/`seed_embeds`: topics already claimed by OTHER subjects in
    this same exam paper (see generate_exam's cross-subject dedup pass) —
    passed straight through to _dedupe_topics so a topic like "नंदा देवी
    राजजात यात्रा" that legitimately fits both uk-history and uk-culture
    only ever gets assigned to one of them."""
    n_topics = max(1, min(count // TOPICS_DIVISOR, TOPICS_CAP))

    official = syllabus.topics_for(subject, exam)
    if official:
        if len(official) >= n_topics:
            picked = random.sample(official, n_topics)
            picked = await _dedupe_topics(picked, subject, exam, official,
                                          seed_topics, seed_embeds)
            logger.info("topics[%s/%s]: %d/%d from official syllabus",
                        subject, exam, len(picked), n_topics)
            return picked
        # official list exhausted — keep ALL of it, top up from PYQ inference
        n_topics -= len(official)
        logger.info("topics[%s/%s]: all %d official + %d PYQ-inferred",
                    subject, exam, len(official), n_topics)
    else:
        official = []

    seed_pyqs = await rag.pyq_lookup(subject, top_k=PYQ_SEED_K, exam=exam)
    if not seed_pyqs:
        return official or [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]

    examples = "\n".join(f"- {p['text'][:300]}" for p in seed_pyqs)
    prompt = (
        f"These are real exam questions for the subject '{subject}':\n\n{examples}\n\n"
        f"What distinct topics/concepts do these exam questions test? "
        f"Return exactly {n_topics} topic strings as a JSON array of strings, "
        f"no prose. Write each topic in Hindi (Devanagari script). "
        f"CRITICAL: every topic must be COMPLETELY DIFFERENT — no two topics should "
        f"overlap or be rewordings of each other. Cover as wide a range as possible."
    )
    try:
        raw = _complete(prompt, max_tokens=1024)
    except Exception as e:
        logger.warning("topic extraction failed (%s) — using subject label", e)
        raw = ""
    topics = [t for t in _parse_json_array(raw) if isinstance(t, str) and t.strip()]
    if not topics:
        return official or [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]
    combined = official + topics[:n_topics]
    return await _dedupe_topics(combined, subject, exam, official,
                                seed_topics, seed_embeds)


# ── the slot engine ──────────────────────────────────────────────────────────

async def _slot_context(subject: str, topic: str, fmt: str,
                        top_k: int = BOOK_TOP_K,
                        query_extra: str = "",
                        exam: str | None = None) -> tuple[list, str, str]:
    """Retrieve one slot's context. Returns (passages, passages_txt, examples_txt).

    `top_k`/`query_extra` support agentic RE-RETRIEVAL: when a draft is rejected
    by the grounding gate ("fact not in passages"), the caller re-invokes this
    with a WIDER top_k and the rejected question's own terms appended to the
    query — so the retry sees MORE and DIFFERENT passages instead of being handed
    the same thin material that produced the ungrounded question. Retrying with
    new evidence beats shipping a doubtful fact.

    `exam` (exam mode only) restricts PYQ style examples to THIS exam's own
    real papers — a vdo-vpdo slot must not imitate group-c's or driver's
    format mix. The any-subject-same-format fallback below intentionally
    KEEPS the exam filter (a rare format's shape still needs to come from
    this exam's own papers, just a different subject within it); only the
    final no-exam-context fallback drops it, and only because at that point
    no example beats a wrong-exam example less than no example at all — see
    the unfiltered call below."""
    search_topic = f"{topic} {query_extra}".strip() if query_extra else topic
    passages = await rag.passage_lookup(search_topic, subject=subject,
                                        top_k=top_k, threshold=PASSAGE_THRESHOLD)
    if not passages:
        # topic string too narrow — fall back to the subject's canonical label
        passages = await rag.passage_lookup(SUBJECT_LABELS.get(subject, subject),
                                            subject=subject, top_k=BOOK_TOP_K,
                                            threshold=0.10)
    examples = await rag.pyq_rag_lookup(topic, subject, top_k=PYQ_TOP_K,
                                        threshold=PYQ_THRESHOLD, format=fmt,
                                        exam=exam)
    if not examples and fmt != "plain":
        # rare format with no nearby example of that format — any-subject example
        # of the SAME FORMAT still teaches the shape better than nothing
        examples = await rag.pyq_rag_lookup(formats.FORMATS[fmt]["label"], subject,
                                            top_k=PYQ_TOP_K, threshold=0.0, format=fmt,
                                            exam=exam)
    if not examples:
        # last resort: drop the exam filter too (no format-true example exists
        # anywhere in this exam's own corpus) — any real PYQ of this subject
        # still teaches better than the placeholder text in etxt below
        examples = await rag.pyq_rag_lookup(topic, subject, top_k=PYQ_TOP_K,
                                            threshold=PYQ_THRESHOLD)

    ptxt = "\n\n".join(f"[{i + 1}] (book: {p.get('book', '')})\n{p.get('text', '')}"
                       for i, p in enumerate(passages)) or "(no material found)"
    etxt = "\n\n".join(f"[{i + 1}] {e.get('text', '')}"
                       for i, e in enumerate(examples)) or \
           "(no example available — use standard UKSSSC framing)"
    return passages, ptxt, etxt


def _seed(*parts) -> int:
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))


def _rejected_terms(draft: dict | None, topic: str) -> str:
    """Pull the entity the rejected draft was ASKING about, to steer the wider
    re-retrieval toward passages that actually contain it. We use the stem +
    the claimed-correct option — that's the fact that failed grounding, so the
    new search should hunt specifically for material stating it."""
    if not isinstance(draft, dict):
        return ""
    parts = []
    stem = draft.get("stem") or draft.get("question") or ""
    if isinstance(stem, str):
        parts.append(stem)
    # the claimed answer text (draft shapes vary: "answer" letter + options, or
    # an explicit answer string) — include whatever names the target fact
    opts = draft.get("options")
    ans = draft.get("answer")
    if isinstance(opts, list) and isinstance(ans, str) and len(ans) == 1:
        idx = "abcd".find(ans.lower())
        if 0 <= idx < len(opts):
            parts.append(str(opts[idx]))
    elif isinstance(ans, str):
        parts.append(ans)
    text = " ".join(parts).strip()
    return text[:200]   # keep the augmentation bounded


async def _gen_slot(subject: str, topic: str, fmt: str, slot_id: int,
                    guard: PaperGuard, slot_sem: asyncio.Semaphore,
                    initial_reason: str = "",
                    exam: str | None = None) -> tuple[dict | None, str]:
    """Generate one question — thin wrapper enforcing the GLOBAL concurrency
    cap via `slot_sem` before doing any real work. Every caller (waves in
    generate_questions, its top-up loop, across every subject a concurrent
    generate_exam() is running) shares the SAME semaphore instance, so total
    in-flight API calls never exceeds GEN_CONCURRENCY no matter how many
    subjects/waves are active at once.

    `slot_sem` is created fresh per top-level call (generate_exam /
    generate_questions — the two functions each Celery task wraps in its own
    asyncio.run()) and passed down, rather than cached as a module global.
    A semaphore is bound to the event loop that created it; asyncio.run()
    makes a NEW loop per job, so a global would occasionally survive a prior
    job's crash/timeout still locked and bound to that job's now-dead loop —
    the next job on the same worker process would then fail immediately with
    "bound to a different event loop" (observed 2026-07-22, job
    6c9771500e9a47ce, right after a prior job hit its Celery soft time
    limit mid-run). Scoping the semaphore to the call, not the process,
    makes that impossible — nothing outlives the job that created it."""
    async with slot_sem:
        return await _gen_slot_inner(subject, topic, fmt, slot_id, guard, initial_reason, exam)


async def _gen_slot_inner(subject: str, topic: str, fmt: str, slot_id: int,
                          guard: PaperGuard, initial_reason: str = "",
                          exam: str | None = None) -> tuple[dict | None, str]:
    """Generate one question. Returns (question, "") or (None, last_reason).
    `initial_reason` injects feedback from a wave-boundary collision so the
    re-run is informed, not a blind re-roll."""
    passages, ptxt, etxt = await _slot_context(subject, topic, fmt, exam=exam)
    if not passages:
        return None, f"no study material for topic '{topic}'"

    system = SLOT_SYSTEM.format(
        format_label=formats.FORMATS[fmt]["label"], topic=topic,
        subject=SUBJECT_LABELS.get(subject, subject),
        contract=formats.FORMATS[fmt]["prompt"],
        examples=etxt, passages=ptxt,
    )
    first_user = f"Write the question now. Format: {fmt}. JSON only."
    if initial_reason:
        first_user += (f"\nNOTE: a previous attempt was rejected — {initial_reason}. "
                       f"Avoid that problem.")
    messages = [{"role": "user", "content": first_user}]
    reason = ""
    grounding_failed = False   # set when the last rejection was the grounding gate
    for attempt in range(MAX_SLOT_ATTEMPTS):
        try:
            raw = await asyncio.to_thread(_draft, system, messages)
        except Exception as e:
            logger.warning("SLOT %s/%s draft failed: %s", topic, fmt, e)
            return None, f"model call failed: {e}"
        draft = _parse_json_object(raw)
        grounding_failed = False
        if draft is None:
            reason = "reply was not a single valid JSON object"
            # log the actual shape so provider quirks (reasoning preambles,
            # fences, truncation) are diagnosable from the worker log alone
            logger.warning("SLOT unparseable reply len=%d head=%r tail=%r",
                           len(raw), raw[:300], raw[-120:] if len(raw) > 300 else "")
        else:
            try:
                q = formats.build(fmt, draft, seed=_seed(subject, topic, slot_id, attempt))
                reason = validate_question(q) or guard.check(q) or ""
                if not reason and fmt == "assertion":
                    reason = await _ar_explain_check(q)
                if not reason:
                    ok, greason = await asyncio.to_thread(ground.check, q, passages)
                    if ok:
                        logger.info("SLOT ok topic=%r fmt=%s attempt=%d", topic, fmt, attempt + 1)
                        return q, ""
                    reason = greason
                    grounding_failed = True   # the fact wasn't in these passages
            except formats.FormatError as e:
                reason = str(e)
        logger.info("SLOT retry topic=%r fmt=%s attempt=%d reason=%s",
                    topic, fmt, attempt + 1, reason)

        # AGENTIC RE-RETRIEVAL: a grounding failure means the passages didn't
        # contain the fact — re-drafting against the SAME passages just invites
        # the same hallucination. Instead, fetch WIDER + DIFFERENT passages
        # (bigger top_k, query augmented by the rejected question's own terms)
        # and rebuild the prompt so the retry reasons over fresh evidence. This
        # is the "retry rather than ship a doubtful fact" loop. Parse/format
        # failures are the model's fault, not the material's — those keep the
        # same passages and just get the reason fed back (rewrite, below).
        if grounding_failed and attempt + 1 < MAX_SLOT_ATTEMPTS:
            wider = BOOK_TOP_K + 3 * (attempt + 1)   # 7, then 10, ...
            q_terms = _rejected_terms(draft, topic)
            new_passages, new_ptxt, new_etxt = await _slot_context(
                subject, topic, fmt, top_k=wider, query_extra=q_terms, exam=exam)
            if new_passages:
                passages, ptxt, etxt = new_passages, new_ptxt, new_etxt
                system = SLOT_SYSTEM.format(
                    format_label=formats.FORMATS[fmt]["label"], topic=topic,
                    subject=SUBJECT_LABELS.get(subject, subject),
                    contract=formats.FORMATS[fmt]["prompt"],
                    examples=etxt, passages=ptxt,
                )
                logger.info("SLOT re-retrieved topic=%r wider_k=%d (grounding miss)",
                            topic, wider)
                # fresh evidence -> a clean draft prompt, not a rewrite of the
                # rejected attempt (which was anchored to the old passages)
                messages = [{"role": "user", "content":
                             f"Write the question now. Format: {fmt}. JSON only. "
                             f"Base it ONLY on a fact explicitly stated in the "
                             f"study material above."}]
                continue

        # INFORMED retry (rewrite): the failure reason goes back to the model verbatim.
        messages = messages[:1] + [
            {"role": "assistant", "content": raw[:2000]},
            {"role": "user", "content": _RETRY_USER.format(reason=reason)},
        ]
    return None, reason


# ── orchestrators ────────────────────────────────────────────────────────────

async def generate_questions(subject: str, count: int,
                             exam: str | None = None,
                             slot_sem: asyncio.Semaphore | None = None,
                             fmt_counts: dict[str, int] | None = None,
                             topics: list[str] | None = None,
                             ) -> tuple[list[dict], dict]:
    """Subject mode (exam=None) or one subject of an exam paper (exam set —
    official-syllabus topic seeding kicks in). Returns (questions, meta) —
    meta carries drop notes for the dashboard; the questions list is always
    clean (no flags).

    `slot_sem` caps total concurrent _gen_slot calls at GEN_CONCURRENCY (see
    _gen_slot's docstring for why this must be created fresh per job, not
    cached as a module global). Callers running multiple subjects concurrently
    (generate_exam) must create ONE semaphore and pass it to every subject's
    call, so the cap is shared across subjects, not per-subject. Subject-mode
    callers (this function invoked directly, its own top-level asyncio.run)
    leave it unset and get one scoped to just this call.

    `fmt_counts` (exam mode only): the pre-decided {format: count} for THIS
    subject, computed once for the whole paper by blueprint.exam_format_plan
    before any subject starts generating (see generate_exam) — real
    per-subject historical format proportions, not one ratio flattened
    across every subject. Subject-mode callers leave this unset and fall
    back to the global format_mix(), unchanged from before this parameter
    existed.

    `topics` (exam mode only): pre-extracted, pre-deduped topics for THIS
    subject, computed once for the whole paper by generate_exam's cross-subject
    dedup pass (see its docstring — _extract_topics/_dedupe_topics only ever
    compared topics WITHIN one subject's own call, so two subjects each
    independently picking "नंदा देवी राजजात यात्रा" — a real culture/history
    crossover topic — never got compared against each other; observed live,
    2026-07-26, Q78/Q83 shipped as the same question twice). Subject-mode
    callers leave this unset and fall back to the original per-subject-only
    extraction, unchanged."""
    if slot_sem is None:
        slot_sem = asyncio.Semaphore(GEN_CONCURRENCY)
    if topics is None:
        topics = await _extract_topics(subject, count, exam=exam)
    if fmt_counts is None:
        fmt_counts = blueprint.allocate(count, blueprint.format_mix())
    # slot list: rare formats first so they land on distinct early topics
    slots = [f for f in ("match", "statement", "assertion", "order")
             for _ in range(fmt_counts.get(f, 0))]
    slots += ["plain"] * fmt_counts.get("plain", 0)

    guard = PaperGuard(total=count)
    out: list[dict] = []
    drops: list[dict] = []

    # WAVE CONCURRENCY: run GEN_CONCURRENCY slots in parallel, then commit their
    # results through the shared PaperGuard sequentially. Every gate still runs;
    # a wave-boundary collision (two parallel slots landing the same answer
    # entity — rare, since each slot has its own topic) re-queues the later slot
    # ONCE with the collision reason injected (informed re-run), then drops.
    pending: list[tuple[int, str, str, str]] = [
        (i, topics[i % len(topics)], fmt, "") for i, fmt in enumerate(slots)
    ]
    while pending:
        wave, pending = pending[:GEN_CONCURRENCY], pending[GEN_CONCURRENCY:]
        results = await asyncio.gather(*[
            _gen_slot(subject, topic, fmt, sid, guard, slot_sem,
                     initial_reason=reason, exam=exam)
            for sid, topic, fmt, reason in wave
        ])
        for (sid, topic, fmt, was_requeued), (q, reason) in zip(wave, results):
            if q is None:
                drops.append({"topic": topic, "format": fmt, "reason": reason})
                continue
            collision = guard.check(q)
            if collision is None:
                guard.commit(q)
                out.append(q)
            elif not was_requeued:
                logger.info("WAVE collision slot=%d: %s — informed re-run", sid, collision)
                pending.append((sid, topic, fmt, collision))
            else:
                drops.append({"topic": topic, "format": fmt,
                              "reason": f"wave collision persisted: {collision}"})

    # top-up: recover the count on fresh topics (same waves) — UNCAPPED except
    # for a circuit breaker (see TOPUP_CIRCUIT_BREAKER_MULTIPLE's docstring):
    # the requested count is a promise, not a target. A fixed topup budget
    # (the old MAX_TOPUP=8) is mathematically guaranteed to under-deliver the
    # moment a paper has more real failures than that budget — observed live
    # on a 100-question paper with 44 drops, capped at recovering only 8,
    # shipping 81/100. Each dropped slot gets up to IN_FORMAT_TOPUP_RETRIES
    # attempts IN ITS OWN ORIGINAL FORMAT before falling back to plain — a
    # paper pre-planned (via blueprint.exam_format_plan) for N match questions
    # must not have every failed match slot silently become plain; that would
    # throw away the whole point of the per-subject-per-format plan through
    # the exact mechanism it was built to fix. `drops` already carries each
    # failure's original `format`, so this is a queue of (format,
    # retries_left) rather than a single hardcoded "plain".
    topup_queue: list[tuple[str, int]] = [
        (d["format"], IN_FORMAT_TOPUP_RETRIES if d["format"] != "plain" else 0)
        for d in drops
    ]
    topup_ceiling = max(count * TOPUP_CIRCUIT_BREAKER_MULTIPLE, 20)
    topup = 0
    while len(out) < count and topup < topup_ceiling:
        need = min(count - len(out), GEN_CONCURRENCY, topup_ceiling - topup)
        batch = []
        for j in range(need):
            if topup_queue:
                fmt, retries_left = topup_queue.pop(0)
            else:
                fmt, retries_left = "plain", 0
            sid = 1000 + topup + j
            topic = topics[(len(slots) + topup + j) % len(topics)]
            batch.append((sid, topic, fmt, retries_left))
        results = await asyncio.gather(*[
            _gen_slot(subject, topic, fmt, sid, guard, slot_sem, exam=exam)
            for sid, topic, fmt, _ in batch
        ])
        for (sid, topic, fmt, retries_left), (q, reason) in zip(batch, results):
            if q is not None and guard.check(q) is None and len(out) < count:
                guard.commit(q)
                out.append(q)
            elif q is None:
                if retries_left > 0:
                    # re-queue in the SAME format, one fewer retry left —
                    # still counts against the circuit breaker overall, just
                    # doesn't give up on the original format immediately
                    topup_queue.append((fmt, retries_left - 1))
                else:
                    drops.append({"topic": topic, "format": f"{fmt}(topup)",
                                 "reason": reason})
        topup += need

    for i, q in enumerate(out, 1):
        q["n"] = i
        q.pop("_claim", None)

    meta = {
        "requested": count,
        "generated": len(out),
        "format_plan": fmt_counts,
        "format_actual": {f: sum(1 for q in out if q.get("format") == f)
                          for f in set(q.get("format", "plain") for q in out)},
        "drops": drops,
        "circuit_breaker_tripped": len(out) < count,
    }
    if len(out) < count:
        # This should be RARE — it means topup_ceiling (5x the paper's own
        # count) was exhausted without reaching the requested total, which
        # only happens if a subject/format combo is structurally unable to
        # ground ANY question (e.g. a corpus with real retrieval hits but no
        # single quotable fact for that topic — see ground.py). Surfaced
        # loudly, not silently absorbed, since the requested count is a
        # promise: this is a real corpus/retrieval gap worth investigating,
        # not an expected outcome.
        logger.error("generate: CIRCUIT BREAKER TRIPPED — only %d/%d for '%s' "
                    "after %d topup attempts (%d drops) — paper is short; "
                    "this subject/format likely has a real grounding gap",
                    len(out), count, subject, topup, len(drops))
    return out, meta


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


async def generate_questions_batched(subject: str, count: int,
                                     exam: str | None = None,
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
        system, user, rfmt = batch_gen.build_batch_prompt(subject, label, sections)
        try:
            raw = await asyncio.to_thread(_draft_structured, system, user, rfmt)
        except Exception as e:
            logger.warning("batch[%s]: draft call failed: %s", subject, e)
            return [], {"subject": subject, "drops": [
                {"topic": s, "format": "plain", "reason": f"batch call failed: {e}"}
                for s, _ in sections]}

        drafts = batch_gen.parse_batch(raw, sections)
        logger.info("batch[%s]: %d sections -> %d drafts", subject,
                    len(sections), len(drafts))

        guard = PaperGuard(total=count)
        for d in drafts:
            passages = d.pop("_passages")
            section = d.pop("_section")
            try:
                q = formats.build("plain", d, seed=_seed(subject, section, 0, 0))
            except formats.FormatError as e:
                drops.append({"topic": section, "format": "plain", "reason": str(e)})
                continue
            reason = validate_question(q) or guard.check(q) or ""
            if reason:
                drops.append({"topic": section, "format": "plain", "reason": reason})
                continue
            ok, greason = await asyncio.to_thread(ground.check, q, passages)
            if not ok:
                drops.append({"topic": section, "format": "plain", "reason": greason})
                continue
            guard.commit(q)
            q["subject"] = subject
            out.append(q)

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

    subjects = [(subject, n) for subject, n in per_subject.items() if n > 0]
    fmt_plan = await asyncio.to_thread(
        blueprint.exam_format_plan, exam, dict(subjects), rag._db())

    raw_topics = await asyncio.gather(*[
        _extract_topics(subject, n, exam=exam) for subject, n in subjects
    ])
    final_topics: dict[str, list[str]] = {}
    pool_topics: list[str] = []
    pool_embeds: list[list[float]] = []
    for (subject, _), topics in zip(subjects, raw_topics):
        official = syllabus.topics_for(subject, exam)
        deduped = await _dedupe_topics(topics, subject, exam, official,
                                       pool_topics, pool_embeds)
        final_topics[subject] = deduped
        new_embeds = await asyncio.gather(*[
            asyncio.to_thread(rag._embed, t) for t in deduped
        ])
        pool_topics.extend(deduped)
        pool_embeds.extend(new_embeds)

    slot_sem = asyncio.Semaphore(GEN_CONCURRENCY)
    results = await asyncio.gather(*[
        generate_questions(subject, n, exam=exam, slot_sem=slot_sem,
                          fmt_counts=fmt_plan[subject],
                          topics=final_topics[subject])
        for subject, n in subjects
    ])

    out: list[dict] = []
    metas: dict[str, dict] = {}
    for (subject, _), (qs, meta) in zip(subjects, results):
        for q in qs:
            q["subject"] = subject
        out.extend(qs)
        metas[subject] = meta
    for i, q in enumerate(out, 1):
        q["n"] = i
    return out, {"exam": exam, "per_subject_plan": per_subject,
                 "format_plan": fmt_plan, "subjects": metas}
