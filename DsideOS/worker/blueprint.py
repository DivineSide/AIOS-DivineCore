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
