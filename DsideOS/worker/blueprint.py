# -*- coding: utf-8 -*-
"""blueprint — the harness owns every count; nothing is left to prose.

Two allocations, same mechanism:
  exam  -> per-subject question counts   (Phase B: numbers locked with the client)
  count -> per-format slot counts        (Phase A: measured default below)

The mixes are MEASURED from the institute's real papers (pyq_chunks, re-ingested
2026-07-12 with format tags + official answers), not invented:

    SELECT format, count(*) FROM pyq_chunks WHERE format IS NOT NULL GROUP BY 1;
    -- plain 87.5% | match 8.9% | statement 1.9% | order 0.7% | assertion 0.5%

    SELECT source_file, subject, count(*) ... GROUP BY exam-family, subject;
    -- e.g. vdo-vpdo: general-gk 32, hindi 19, uk-gs 12, uk-history 12,
    --      uk-culture 12, uk-geography 10, computer 4  (percent)

`allocate()` turns (total, mix) into EXACT integer counts via largest-remainder —
they always sum to total, so a 100-question paper has 100 questions by
construction, never "about 100 because the model felt like it".

Client tuning knobs (tomorrow's session): env GEN_FORMAT_MIX and
GEN_SUBJECT_MIX_<EXAM> override the measured defaults without a code change,
e.g. GEN_FORMAT_MIX="plain:80,match:12,statement:5,assertion:2,order:1".
"""
from __future__ import annotations

import os
import random

# ── measured defaults (see docstring queries) ────────────────────────────────

# Per-format share of generated questions. "figure" is deliberately absent —
# we cannot generate diagrams. Its ~0.4% share is folded into plain.
FORMAT_MIX: dict[str, float] = {
    "plain":     0.879,
    "match":     0.089,
    "statement": 0.019,
    "order":     0.007,
    "assertion": 0.006,
}

# Per-exam subject shares, measured from that exam family's real papers.
# PHASE B: these are the OPENING PROPOSAL for the client session — final
# numbers get locked with the client and can be overridden via env.
SUBJECT_MIX: dict[str, dict[str, float]] = {
    "vdo-vpdo": {
        "general-gk": 0.32, "hindi": 0.19, "uk-general-studies": 0.12,
        "uk-history": 0.12, "uk-culture": 0.12, "uk-geography": 0.10,
        "computer": 0.03,
    },
    "lekhpal-patwari": {
        "general-gk": 0.38, "hindi": 0.26, "uk-general-studies": 0.10,
        "uk-geography": 0.10, "uk-history": 0.06, "uk-culture": 0.06,
        "computer": 0.04,
    },
    "group-c": {
        "general-gk": 0.40, "uk-history": 0.20, "uk-general-studies": 0.12,
        "uk-culture": 0.11, "uk-geography": 0.10, "hindi": 0.04,
        "computer": 0.03,
    },
    # police-constable (आरक्षी जनपदीय पुलिस/PAC-IRB, Advt 65/2024): NO measured
    # papers in pyq_chunks yet, so this mix is DERIVED, not measured — the
    # part-level split is OFFICIAL (परिशिष्ट-1: हिंदी 20 / GK-GS 40 / UK 40,
    # verified identical to the Group C master syllabus), and the within-part
    # sub-splits borrow group-c's measured ratios. तर्कशक्ति (reasoning) sits
    # inside the GK-GS part officially but has no generation path yet — its
    # share is folded into general-gk until reasoning-mode ships.
    "police-constable": {
        "hindi": 0.20,
        "general-gk": 0.37, "computer": 0.03,               # भाग-2 = 0.40
        "uk-history": 0.15, "uk-general-studies": 0.09,     # भाग-3 = 0.40
        "uk-culture": 0.08, "uk-geography": 0.08,
    },
}


def _env_mix(var: str) -> dict[str, float] | None:
    """Parse 'key:share,key:share' env override; shares normalize to 1."""
    raw = os.environ.get(var, "").strip()
    if not raw:
        return None
    try:
        parts = dict(p.split(":") for p in raw.split(","))
        mix = {k.strip(): float(v) for k, v in parts.items()}
        total = sum(mix.values())
        if total <= 0:
            return None
        return {k: v / total for k, v in mix.items()}
    except (ValueError, TypeError):
        return None


def format_mix() -> dict[str, float]:
    return _env_mix("GEN_FORMAT_MIX") or FORMAT_MIX


def subject_mix(exam: str) -> dict[str, float]:
    override = _env_mix(f"GEN_SUBJECT_MIX_{exam.upper().replace('-', '_')}")
    if override:
        return override
    if exam not in SUBJECT_MIX:
        raise ValueError(f"Unknown exam family {exam!r}. Known: {sorted(SUBJECT_MIX)}")
    return SUBJECT_MIX[exam]


# ── the allocator ────────────────────────────────────────────────────────────

def allocate(total: int, mix: dict[str, float]) -> dict[str, int]:
    """Largest-remainder allocation: exact integer counts that sum to `total`.

    Every key keeps its floor; remaining units go to the largest fractional
    remainders (ties broken by larger share, then key order for determinism).
    Keys can get 0 (a 10-question paper simply has no assertion slot — correct,
    not a bug: rare formats appear only when the paper is big enough to
    deserve them, same as real papers)."""
    if total < 0:
        raise ValueError("total must be >= 0")
    shares = {k: total * v for k, v in mix.items()}
    counts = {k: int(s) for k, s in shares.items()}
    leftover = total - sum(counts.values())
    order = sorted(mix, key=lambda k: (-(shares[k] - counts[k]), -mix[k], k))
    for k in order[:leftover]:
        counts[k] += 1
    return counts


# ── per-subject format planning (2026-07-22) ────────────────────────────────
# WHY: the global FORMAT_MIX above is measured across ALL subjects combined,
# then applied identically to every subject's own slice of the paper. Real
# papers don't work that way — some subjects (e.g. history) carry far more
# match-the-following / statement questions than others (e.g. computer) in
# the actual PYQ corpus. Flattening everyone to one ratio, at real per-subject
# sizes (5-16 questions), rounds rare formats to 0 for most subjects even when
# the paper-level plan calls for them elsewhere. This section computes a
# REAL per-subject-per-format mix from pyq_chunks instead of guessing, then
# reuses allocate() (same largest-remainder mechanics, no new algorithm) to
# turn it into exact counts. Exam-mode only — subject mode has no exam
# context to scope the measurement to (see generate.py's own docstrings).

ALPHA = 5.0   # additive-smoothing strength: how hard sparse subjects get
              # pulled toward the global FORMAT_MIX (see subject_format_mix)
JITTER_SPREAD = 0.15   # ±15% relative — "small range for random" per spec


def subject_format_mix(exam: str, subject: str, conn) -> dict[str, float]:
    """Real per-format shares for ONE subject within ONE exam, measured from
    pyq_chunks. Falls back exam-scoped -> subject-global (any exam) -> the
    plain FORMAT_MIX when a subject has too little real data to trust on its
    own — additive smoothing blends toward FORMAT_MIX proportionally to
    sample size, so 3 real "match" questions don't produce a 100% match
    ratio, but 200 real examples barely move off their own true ratio.
    `conn` is a short-lived sync psycopg2 connection (planning-time
    aggregate query, not the async RAG lookup path in rag/query.py)."""
    def _counts(where_exam: bool) -> dict[str, int]:
        sql = ("SELECT format, count(*) FROM pyq_chunks "
               "WHERE subject = %s AND format IS NOT NULL"
               + (" AND exam = %s" if where_exam else ""))
        params = (subject, exam) if where_exam else (subject,)
        with conn.cursor() as cur:
            cur.execute(sql + " GROUP BY format", params)
            return {fmt: n for fmt, n in cur.fetchall()}

    counts = _counts(where_exam=True)
    if not counts:
        counts = _counts(where_exam=False)   # widen: this subject, any exam
    if not counts:
        return dict(FORMAT_MIX)              # no real data at all — plain default

    total_n = sum(counts.values())
    return {
        fmt: (counts.get(fmt, 0) + ALPHA * base_share) / (total_n + ALPHA)
        for fmt, base_share in FORMAT_MIX.items()
    }


def _jitter(mix: dict[str, float], rng: random.Random,
           spread: float = JITTER_SPREAD) -> dict[str, float]:
    """Multiply each share by (1 + U(-spread, spread)), renormalize to sum 1.
    Randomizes the MIX, not the final integer counts — allocate()'s
    sum-to-total guarantee is preserved automatically since it always
    operates on a valid (summing-to-1) distribution."""
    jittered = {k: v * (1 + rng.uniform(-spread, spread)) for k, v in mix.items()}
    total = sum(jittered.values())
    return {k: v / total for k, v in jittered.items()}


def exam_format_plan(exam: str, per_subject: dict[str, int], conn,
                     seed: int | None = None) -> dict[str, dict[str, int]]:
    """The full pre-decision: for every subject in this exam's paper, compute
    its real (smoothed) format mix, jitter it for run-to-run variation, then
    allocate() exact integer counts. Returns {subject: {format: count}},
    each subject's counts summing to per_subject[subject].

    Called ONCE per exam, before generation starts — the harness owns this
    decision up front, same philosophy as subject_mix/format_mix above, just
    scoped per-subject instead of flattened globally. `seed=None` (default)
    means real entropy-seeded variation across runs; pass an int for
    deterministic tests. On any DB failure, falls back to today's exact
    global-FORMAT_MIX-per-subject behavior for the whole exam — a planning
    query failing must never block a generation job."""
    rng = random.Random(seed)
    try:
        return {
            subject: allocate(n, _jitter(subject_format_mix(exam, subject, conn), rng))
            for subject, n in per_subject.items()
        }
    except Exception:
        return {subject: allocate(n, format_mix()) for subject, n in per_subject.items()}
