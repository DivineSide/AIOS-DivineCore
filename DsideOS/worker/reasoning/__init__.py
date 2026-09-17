# -*- coding: utf-8 -*-
"""reasoning — तर्कशक्ति questions generated ENTIRELY BY CODE. No model call.

WHY THIS EXISTS: every other question the pipeline produces has the same
weakness — nothing verifies the fact is true. The RAG path constrains the model
to supplied passages; the taxonomy path trusts the model's own knowledge. Both
can ship a confidently-wrong answer.

Reasoning is the exception, and that is the entire point. A direction-and-
distance question depends only on the walk WE invented, so the answer is
arithmetic, not an assertion about the world. Code picks the parameters,
computes the answer from those same parameters, and fills a template. The
answer cannot be wrong unless the arithmetic is wrong — and arithmetic is
unit-testable once, forever (tests/test_reasoning.py).

Consequently NO GATE APPLIES on this path (see the plan's exemption table):
validate_gen's checks and PaperGuard are all proxies for LLM failure modes that
cannot occur here — a numeric answer is CORRECT for a distance question, a
4-digit series term is not a hallucinated date, and two questions may both
legitimately answer "5". The tests are the gate.

VARIETY has two independent axes that multiply:
  semantic — the parameters (walk legs, cipher rule). Changes the answer.
  cosmetic — names, verbs, units, phrasings from pools.py. Changes nothing.
There is no reuse-tracking table (unlike taxonomy leaves): the seed IS the
identity and the space is large enough that collisions are negligible.

Interface:
    generate(count, seed) -> list[question dict]
    TYPES                 -> {name: module}     # the registry
"""
from __future__ import annotations

import logging
import random

from . import (arrangement, calendar_year, clock, coded_relations, coding,
               dice, direction, grouping, household, lettersum, relations,
               series, sufficiency, triangles, venn)
from . import figseries

logger = logging.getLogger(__name__)

# The registry. Each module exposes `generate(rng) -> dict`.
#
# _allocate spreads a block evenly across every entry here, so a 10-question
# block gets roughly one of each type rather than a random draw that could
# return five direction questions. Real papers do exactly this.
TYPES = {
    "direction": direction,
    "series": series,
    "coding": coding,
    "relations": relations,
    "arrangement": arrangement,
    "lettersum": lettersum,
    "calendar_year": calendar_year,
    "grouping": grouping,
    "household": household,
    "clock": clock,
    "coded_relations": coded_relations,
    "sufficiency": sufficiency,
    # FIGURE types: these return a `_figure` spec that reasoning/render.py
    # turns into a PNG. The generators themselves still touch no disk.
    "dice": dice,
    "triangles": triangles,
    "venn": venn,
    "figseries": figseries,
}

# Attempts to find a distinct stem before giving up on a slot. Collisions are
# rare (the parameter space per type is in the thousands) but not impossible on
# a small type set, and a duplicate stem in one paper is the one structural
# defect a generator can still produce.
_MAX_STEM_ATTEMPTS = 12


def _allocate(count: int, types: list[str], rng: random.Random) -> list[str]:
    """Even type spread, in an order that varies but never clusters.

    Deliberately NOT blueprint.allocate: that distributes by measured share,
    but reasoning types have no measured share (the syllabus gives no
    per-section counts at all — see corpus/reasoning-reference/SURVEY.md). An
    even spread is what the real papers show.

    NOT a plain shuffle either. Round-robin then shuffle was the first attempt
    and it defeated its own purpose: measured 51/200 blocks with a run of 3+
    identical types, including three consecutive coding questions. Instead the
    types are shuffled WITHIN each round, which varies the order every run
    while guaranteeing all N types appear before any repeats.

    Complexity: O(count).
    """
    out: list[str] = []
    while len(out) < count:
        round_ = types[:]
        rng.shuffle(round_)
        # Avoid a seam: a round ending on X followed by one starting on X is
        # the only way two identical types can still land adjacent.
        if out and round_[0] == out[-1] and len(round_) > 1:
            round_[0], round_[1] = round_[1], round_[0]
        out.extend(round_)
    return out[:count]


def generate(count: int, seed: int | None = None) -> list[dict]:
    """`count` reasoning questions. No I/O, no network, no model.

    Deterministic for a given seed: the same seed reproduces the same paper,
    which is what makes a failure reproducible from the job record alone.

    Stems are guaranteed distinct within the returned block; a type that cannot
    produce a fresh stem in _MAX_STEM_ATTEMPTS is skipped rather than retried
    forever, and the shortfall is logged (it would mean a generator's parameter
    space is far smaller than intended).

    Complexity: O(count) generator calls, each O(1). No allocation beyond the
    output list.
    """
    rng = random.Random(seed)
    plan = _allocate(count, list(TYPES), rng)

    out: list[dict] = []
    seen_stems: set[str] = set()
    for type_name in plan:
        mod = TYPES[type_name]
        for _ in range(_MAX_STEM_ATTEMPTS):
            q = mod.generate(rng)
            # Dedup on BOTH the semantic key and the rendered stem.
            #
            # The semantic half catches questions that differ only cosmetically:
            # two relation questions asking "मेरे पिता के भाई" with different
            # speaker names are different strings but the same question (11 of
            # 300 blocks before `_dedup_key` existed).
            #
            # The stem half catches the inverse, which `_dedup_key` alone let
            # through: two `lettersum` questions with DIFFERENT word sets can
            # draw the same phrasing and the same अधिकतम/न्यूनतम form, so the
            # stems render identically while the keys differ. A paper with two
            # visually identical questions is broken however distinct their
            # internals are.
            # The VISIBLE key is stem + options, not the stem alone.
            #
            # `lettersum` puts its whole question in the OPTIONS — the stem is
            # boilerplate — so stem-only dedup saw just 6 distinct questions out
            # of 4,975 and ran the generator dry inside one block. Two questions
            # a student could tell apart at a glance are different questions,
            # and the options are on the page too.
            #
            # For a FIGURE question the visible content is the picture, and the
            # stem can be pure boilerplate: `figseries` uses ONE fixed stem for
            # every question by design (only the strip changes), so stem+options
            # made every figseries question after the first look like a
            # duplicate — a 100-question block lost 5 questions to it. The spec
            # is the drawing, so fold it in.
            fig = q.get("_figure") or q.get("_figure_options")
            stem_key = " ".join(q["stem"].split()) + "||" + "|".join(
                sorted(q["options"])) + ("||" + repr(fig) if fig else "")
            sem_key = q.get("_dedup_key")
            # Reject if EITHER half has been seen — a tuple key would only
            # collide when both matched, which let a fresh word set reuse an
            # already-printed stem.
            if stem_key in seen_stems or (sem_key and sem_key in seen_stems):
                continue
            seen_stems.add(stem_key)
            if sem_key:
                seen_stems.add(sem_key)
            out.append(q)
            break
        else:
            logger.warning(
                "reasoning[%s]: no distinct stem in %d attempts — the "
                "parameter space may be smaller than intended",
                type_name, _MAX_STEM_ATTEMPTS)

    if len(out) < count:
        logger.warning("reasoning: wanted %d questions, produced %d",
                       count, len(out))
    return out
