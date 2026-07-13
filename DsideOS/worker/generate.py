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
    generate_exam(exam, total)         -> (questions, meta)   # Phase B shell —
        per-exam quotas get locked WITH THE CLIENT; blueprint's measured
        SUBJECT_MIX is the opening proposal.
"""
import asyncio
import json
import logging
import os
import sys
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

import blueprint  # noqa: E402
import formats  # noqa: E402
import ground  # noqa: E402
from validate_gen import PaperGuard, validate_question  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
# Drafting is the intelligence step — worth the smart tier. Output is small
# (facts only, code builds the rest), so cost stays ~$1 per 100-question paper.
GEN_MODEL = os.environ.get("GEN_MODEL", SONNET)

GEN_PROVIDER = os.environ.get("GEN_PROVIDER", "anthropic").lower()
SARVAM_MODEL = os.environ.get("SARVAM_MODEL", "sarvam-105b")
SARVAM_BASE_URL = "https://api.sarvam.ai/v1"

TOPICS_DIVISOR = 2       # ~count/2 distinct topics (was 4 — variety collapsed)
TOPICS_CAP = 40
PYQ_SEED_K = 40          # random PYQs fed to topic extraction
BOOK_TOP_K = 4           # passages per slot
PYQ_TOP_K = 2            # style examples per slot
PASSAGE_THRESHOLD = 0.20
PYQ_THRESHOLD = 0.10

MAX_SLOT_ATTEMPTS = 3    # 1 draft + up to 2 informed retries per slot
MAX_TOPUP = 8            # extra slots tried when drops leave the paper short
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
SLOT_SYSTEM = """You are an Indian competitive-exam question writer (UKSSSC-style).
Write ONE question of the format: {format_label} — topic: "{topic}" (subject: {subject}).

Return ONLY this JSON object (no prose, no fences):
{contract}

RULES:
- Language: Hindi (Devanagari). English proper nouns/technical terms stay English.
- Every fact you use MUST be explicitly stated in the STUDY MATERIAL below.
  Do not use your own knowledge — an unverifiable fact gets your question rejected.
- Distractors must be plausible: same category as the correct answer (a wrong
  year near the right one, a sibling dynasty, a neighbouring district).
- Mirror the framing and register of the REAL PAST QUESTIONS shown.

━━━ REAL PAST QUESTIONS (style reference) ━━━
{examples}

━━━ STUDY MATERIAL (your ONLY source of facts) ━━━
{passages}"""

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


def _draft_sarvam(system: str, messages: list[dict]) -> str:
    # sarvam-105b is a REASONING model: without reasoning_effort it thinks at
    # essay length into a hidden reasoning_content field, hits max_tokens, and
    # returns EMPTY content (finish_reason=length) on every complex prompt.
    # reasoning_effort=low bounds the think so the answer actually arrives.
    # max_tokens: starter tier hard-caps at 4096; 3000 leaves room for
    # ~1300 reasoning tokens + the JSON.
    resp = _sarvam_client().chat.completions.create(
        model=SARVAM_MODEL, max_tokens=3000,
        extra_body={"reasoning_effort":
                    os.environ.get("SARVAM_REASONING", "low")},
        messages=[{"role": "system", "content": system}] + messages,
    )
    choice = resp.choices[0]
    out = (choice.message.content or "").strip()
    if not out:
        logger.warning("SARVAM empty content (finish=%s, completion_toks=%s)",
                       choice.finish_reason,
                       getattr(resp.usage, "completion_tokens", "?"))
    return out


def _draft(system: str, messages: list[dict]) -> str:
    if GEN_PROVIDER == "sarvam":
        return _draft_sarvam(system, messages)
    return _draft_anthropic(system, messages)


def _parse_json_object(text: str) -> dict | None:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(t[start:end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
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


async def _extract_topics(subject: str, count: int) -> list[str]:
    """Derive distinct exam topics from a random sample of the subject's real
    PYQs (topic signal comes from what the exam actually tests)."""
    n_topics = max(1, min(count // TOPICS_DIVISOR, TOPICS_CAP))

    seed_pyqs = await rag.pyq_lookup(subject, top_k=PYQ_SEED_K)
    if not seed_pyqs:
        return [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]

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
        msg = _client().messages.create(
            model=HAIKU, max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip() if msg.content else ""
    except Exception as e:
        logger.warning("topic extraction failed (%s) — using subject label", e)
        raw = ""
    topics = [t for t in _parse_json_array(raw) if isinstance(t, str) and t.strip()]
    if not topics:
        return [SUBJECT_LABELS.get(subject, subject.replace("-", " "))]
    return topics[:n_topics]


# ── the slot engine ──────────────────────────────────────────────────────────

async def _slot_context(subject: str, topic: str, fmt: str) -> tuple[list, str, str]:
    """Retrieve one slot's context. Returns (passages, passages_txt, examples_txt)."""
    passages = await rag.passage_lookup(topic, subject=subject,
                                        top_k=BOOK_TOP_K, threshold=PASSAGE_THRESHOLD)
    if not passages:
        # topic string too narrow — fall back to the subject's canonical label
        passages = await rag.passage_lookup(SUBJECT_LABELS.get(subject, subject),
                                            subject=subject, top_k=BOOK_TOP_K,
                                            threshold=0.10)
    examples = await rag.pyq_rag_lookup(topic, subject, top_k=PYQ_TOP_K,
                                        threshold=PYQ_THRESHOLD, format=fmt)
    if not examples and fmt != "plain":
        # rare format with no nearby example of that format — any-subject example
        # of the SAME FORMAT still teaches the shape better than nothing
        examples = await rag.pyq_rag_lookup(formats.FORMATS[fmt]["label"], subject,
                                            top_k=PYQ_TOP_K, threshold=0.0, format=fmt)
    if not examples:
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


async def _gen_slot(subject: str, topic: str, fmt: str, slot_id: int,
                    guard: PaperGuard, initial_reason: str = "") -> tuple[dict | None, str]:
    """Generate one question. Returns (question, "") or (None, last_reason).
    `initial_reason` injects feedback from a wave-boundary collision so the
    re-run is informed, not a blind re-roll."""
    passages, ptxt, etxt = await _slot_context(subject, topic, fmt)
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
    for attempt in range(MAX_SLOT_ATTEMPTS):
        try:
            raw = await asyncio.to_thread(_draft, system, messages)
        except Exception as e:
            logger.warning("SLOT %s/%s draft failed: %s", topic, fmt, e)
            return None, f"model call failed: {e}"
        draft = _parse_json_object(raw)
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
                if not reason:
                    ok, greason = await asyncio.to_thread(ground.check, q, passages)
                    if ok:
                        logger.info("SLOT ok topic=%r fmt=%s attempt=%d", topic, fmt, attempt + 1)
                        return q, ""
                    reason = greason
            except formats.FormatError as e:
                reason = str(e)
        logger.info("SLOT retry topic=%r fmt=%s attempt=%d reason=%s",
                    topic, fmt, attempt + 1, reason)
        # INFORMED retry: the failure reason goes back to the model verbatim.
        messages = messages[:1] + [
            {"role": "assistant", "content": raw[:2000]},
            {"role": "user", "content": _RETRY_USER.format(reason=reason)},
        ]
    return None, reason


# ── orchestrators ────────────────────────────────────────────────────────────

async def generate_questions(subject: str, count: int) -> tuple[list[dict], dict]:
    """Subject mode. Returns (questions, meta) — meta carries drop notes for the
    dashboard; the questions list is always clean (no flags)."""
    topics = await _extract_topics(subject, count)
    fmt_counts = blueprint.allocate(count, blueprint.format_mix())
    # slot list: rare formats first so they land on distinct early topics
    slots = [f for f in ("match", "statement", "assertion", "order")
             for _ in range(fmt_counts.get(f, 0))]
    slots += ["plain"] * fmt_counts.get("plain", 0)

    guard = PaperGuard()
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
            _gen_slot(subject, topic, fmt, sid, guard, initial_reason=reason)
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

    # top-up: recover the count with plain questions on fresh topics (same waves)
    topup = 0
    while len(out) < count and topup < MAX_TOPUP:
        need = min(count - len(out), GEN_CONCURRENCY, MAX_TOPUP - topup)
        batch = [(1000 + topup + j, topics[(len(slots) + topup + j) % len(topics)])
                 for j in range(need)]
        results = await asyncio.gather(*[
            _gen_slot(subject, topic, "plain", sid, guard) for sid, topic in batch
        ])
        for (sid, topic), (q, reason) in zip(batch, results):
            if q is not None and guard.check(q) is None and len(out) < count:
                guard.commit(q)
                out.append(q)
            elif q is None:
                drops.append({"topic": topic, "format": "plain(topup)", "reason": reason})
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
    }
    if len(out) < count:
        logger.warning("generate: only %d/%d for '%s' (%d drops)",
                       len(out), count, subject, len(drops))
    return out, meta


async def generate_exam(exam: str, total: int) -> tuple[list[dict], dict]:
    """Exam mode — PHASE B SHELL. Mechanics are final (harness owns the counts);
    the per-exam SUBJECT_MIX numbers are the client-session deliverable."""
    per_subject = blueprint.allocate(total, blueprint.subject_mix(exam))
    out: list[dict] = []
    metas: dict[str, dict] = {}
    for subject, n in per_subject.items():
        if n == 0:
            continue
        qs, meta = await generate_questions(subject, n)
        for q in qs:
            q["subject"] = subject
        out.extend(qs)
        metas[subject] = meta
    for i, q in enumerate(out, 1):
        q["n"] = i
    return out, {"exam": exam, "per_subject_plan": per_subject, "subjects": metas}
