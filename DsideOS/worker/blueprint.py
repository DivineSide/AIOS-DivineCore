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
        "general-gk": 0.22, "hindi": 0.19, "uk-general-studies": 0.12,
        "uk-history": 0.12, "uk-culture": 0.12, "uk-geography": 0.10,
        "computer": 0.03, "reasoning": 0.10,
    },
    "lekhpal-patwari": {
        "general-gk": 0.28, "hindi": 0.26, "uk-general-studies": 0.10,
        "uk-geography": 0.10, "uk-history": 0.06, "uk-culture": 0.06,
        "computer": 0.04, "reasoning": 0.10,
    },
    "group-c": {
        "general-gk": 0.30, "uk-history": 0.20, "uk-general-studies": 0.12,
        "uk-culture": 0.11, "uk-geography": 0.10, "hindi": 0.04,
        "computer": 0.03, "reasoning": 0.10,
    },
    # police-constable (आरक्षी जनपदीय पुलिस/PAC-IRB, Advt 65/2024): NO measured
    # papers in pyq_chunks yet, so this mix is DERIVED, not measured — the
    # part-level split is OFFICIAL (परिशिष्ट-1: हिंदी 20 / GK-GS 40 / UK 40,
    # verified identical to the Group C master syllabus), and the within-part
    # sub-splits borrow group-c's measured ratios. तर्कशक्ति (reasoning) sits
    # inside the GK-GS part officially and SHIPPED 2026-09-15 (worker/reasoning,
    # code-generated, no model call) — its 0.10 is carved back out of
    # general-gk, which had been absorbing it.
    "police-constable": {
        "hindi": 0.20,
        "general-gk": 0.27, "computer": 0.03,               # भाग-2 = 0.40
        "reasoning": 0.10,                                  # ...incl. तर्कशक्ति
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


# ── difficulty planning (2026-09-12) ────────────────────────────────────────
# Real papers grade difficulty, not just format. The target distribution is the
# client's, from how UKSSSC papers actually read: half the paper answerable by
# any prepared candidate, a third needing real preparation, a fifth genuinely
# separating the top scorers.
#
# DIFFICULTY IS INDEPENDENT OF FORMAT. It is tempting to call match/assertion
# "hard" and be done, but the measured format mix is ~87% plain — tying the two
# together caps hard at ~13% and the 20% target becomes unreachable. So a plain
# question can be hard (a niche fact, or a stem needing inference) and a match
# can be easy (four obvious pairings). Complex formats SKEW harder in practice;
# they are not locked to it.
DIFFICULTY_MIX: dict[str, float] = {
    "easy":     0.50,
    "moderate": 0.30,
    "hard":     0.20,
}


def difficulty_mix() -> dict[str, float]:
    """DIFFICULTY_MIX, overridable via GEN_DIFFICULTY_MIX (same env-parsing
    contract as format_mix/subject_mix — see _env_mix)."""
    return _env_mix("GEN_DIFFICULTY_MIX") or DIFFICULTY_MIX


def plan_questions(count: int, fmt_counts: dict[str, int],
                   rng: random.Random | None = None) -> list[dict]:
    """Pair each of `count` questions with a (format, difficulty).

    Returns [{"format": str, "difficulty": str}, ...] of exactly len == count.

    The two axes are allocated INDEPENDENTLY (see DIFFICULTY_MIX's note), then
    zipped after shuffling the difficulty list — so difficulty is not correlated
    with format by construction, but a paper still gets exactly its planned
    counts of each. Shuffling (rather than sorting hard onto complex formats)
    is what keeps a hard `plain` question possible.

    Complexity: O(count log count) from the shuffle; count <= ~40 per subject.
    Tradeoff: independent allocation can produce an "easy assertion", which is
    rarer in real papers than a hard one. Accepted — the alternative (weighting
    difficulty by format) reintroduces the 13% ceiling this design exists to
    avoid. The prompt tells the model to make an easy assertion genuinely easy.
    """
    rng = rng or random.Random()
    diff_counts = allocate(count, difficulty_mix())
    difficulties = [d for d, n in diff_counts.items() for _ in range(n)]
    rng.shuffle(difficulties)

    formats = [f for f, n in fmt_counts.items() for _ in range(n)]
    # fmt_counts comes from allocate() on the same count, but a caller could
    # pass a stale plan — pad/trim to `count` rather than silently misalign.
    if len(formats) < count:
        formats += ["plain"] * (count - len(formats))
    formats = formats[:count]
    rng.shuffle(formats)

    return [{"format": f, "difficulty": d}
            for f, d in zip(formats, difficulties)]


def group_by_format(plan: list[dict]) -> dict[str, list[str]]:
    """{format: [difficulty, ...]} — the batching key.

    Generation runs ONE call per (subject, format) so each batch has a single
    strict JSON schema; a mixed-shape batch cannot be schema-enforced (a schema
    cannot say "item 3 is a match and item 4 is plain"). Difficulties ride along
    per question inside each format's batch.
    """
    out: dict[str, list[str]] = {}
    for q in plan:
        out.setdefault(q["format"], []).append(q["difficulty"])
    return out


# ── per-subject format planning: ARCHIVED 2026-09-13 ────────────────────────
# subject_format_mix / _jitter / exam_format_plan lived here until the round-2
# rebuild. generate_exam() no longer runs a format pre-pass — the batched
# engine plans format inside generate_questions_batched — so all three had
# zero callers. Moved to .archive/dsideos-dead-code/, which keeps the measured
# per-subject-format reasoning (history really does carry more match questions
# than computer) available if that realism is wanted back.
