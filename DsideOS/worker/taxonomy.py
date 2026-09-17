# -*- coding: utf-8 -*-
"""taxonomy — question-sized topic leaves, sampled like passages.

WHAT THIS IS: a no-RAG topic source. `sample.sections_for` hands the model a
book section plus real passages; this hands it a syllabus LEAF and nothing
else, because for national subjects (general-gk, hindi, computer) the corpus
has ZERO sectioned passages and the model's own knowledge is the better source
anyway. The leaf's job is to be NARROW — given "पुर्तगाली मूल के आगत शब्द" the
model cannot fall back to the five famous आगत words the way "आगत शब्द" invites.

WHERE THE DATA COMES FROM: worker/taxonomy_data/<exam-family>/<subject>.json, authored
once by reading the official syllabus bullet alongside ~90 real PYQs per subject
(the PYQs show what the commission actually examines; the bullet alone does not).
Regenerating is a human+agent task, not a runtime call — see RAG_ROADMAP §12.
Leaves carry no difficulty tag (dropped 2026-09-13 — see the taxonomy files'
own "note" field): a leaf is just a topic label, nothing else.

CROSS-PAPER REUSE TRACKING (2026-09-13, migration 009): same mechanic as
rag/sample.py's passage cooldown, applied to leaves instead of rows, because a
leaf pool this size (uk-culture: 124) has real collision odds between two
consecutive papers without it. Leaves have no integer id (they live in a JSON
file, not a DB table), so cooldown state is tracked in a small side table keyed
by (subject, family, label) — see migration 009's docstring for why a string
key is the right tradeoff here. used_ago is age-in-generations, identical
semantics to passages: 0 = just used, 1..5 = cooling down, NULL = eligible.

Shape mirrors sample.sections_for deliberately, so generate.py can swap sources
without knowing which it got:
    sections_for(subject, n, conn) -> [(leaf_label, []), ...]
The empty list is the passage slot. Callers MUST NOT assume passages exist —
build_batch_prompt already renders an empty list as the no-RAG prompt branch,
which is why NORAG_SYSTEM replaces any prompt line that tells the model to
quote its source.

Interface:
    available(subject, exam) -> bool               # is there a taxonomy for this?
    sections_for(subject, n, conn) -> [(label, [])] # sample.sections_for-shaped
    leaves_for(subject, n, conn) -> list[dict]       # the underlying leaf dicts
    mark_used(subject, labels, conn) -> None         # call once per paper
    advance_generation(family, conn) -> None         # call once per paper, after
    stats(subject) -> dict                           # counts, for diagnostics
"""
from __future__ import annotations

import json
import logging
import random
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Taxonomies live NEXT TO this module, not under corpus/, deliberately: they
# are authored source (1,354 hand-written leaves), not ingested corpus data.
# corpus/ is gitignored wholesale for books/PDFs/OCR output, which would have
# left generation's topic layer untracked and one disk loss from breaking 5 of
# 7 subjects.
TAXONOMY_DIR = Path(__file__).resolve().parent / "taxonomy_data"

# Exam families sharing the UKSSSC master syllabus all read one taxonomy dir.
# A genuinely different syllabus (Livestock Extension Officer, Driver) would get
# its own directory here, which is the whole point of keying by family.
DEFAULT_FAMILY = "uksssc-master"

# Generations a leaf stays ineligible after use. Same constant and same
# reasoning as rag/sample.py's REUSE_COOLDOWN — kept independently
# configurable (not imported from sample.py) because the two pools are
# different sizes and may need different tuning once Phoenix shows real
# exhaustion rates for each.
REUSE_COOLDOWN = 5


def _path(subject: str, family: str = DEFAULT_FAMILY) -> Path:
    return TAXONOMY_DIR / family / f"{subject}.json"


@lru_cache(maxsize=32)
def _load(subject: str, family: str = DEFAULT_FAMILY) -> list[dict] | None:
    """Flatten the tree to a leaf list ONCE per process.

    Returns [{"label", "facet", "bullet"}, ...] or None when no taxonomy file
    exists — callers fall back to the RAG path.

    Complexity: O(total leaves) on first call, O(1) cached after. ~470 leaves
    for the largest subject, so the parse is sub-millisecond and the cache
    exists to avoid re-reading the file per batch, not for speed.

    Tradeoff: lru_cache means an edited taxonomy needs a worker restart to take
    effect. That is correct for a Celery worker (files are baked into the image)
    and is why authoring is offline — if these ever become hot-editable, drop
    the cache and stat() the file instead.
    """
    p = _path(subject, family)
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        # A malformed taxonomy must not take generation down — the RAG path is
        # still there. Loud log, soft failure.
        logger.error("taxonomy[%s]: unreadable (%s) — falling back", subject, e)
        return None

    out: list[dict] = []
    for bullet in doc.get("bullets", []):
        btext = bullet.get("text", "")
        for facet in bullet.get("facets", []):
            flabel = facet.get("label", "")
            for leaf in facet.get("leaves", []):
                label = (leaf.get("label") or "").strip()
                if not label:
                    continue
                out.append({"label": label, "facet": flabel, "bullet": btext})
    if not out:
        logger.error("taxonomy[%s]: file present but no leaves", subject)
        return None
    return out


def available(subject: str, exam: str | None = None,
              family: str = DEFAULT_FAMILY) -> bool:
    """True when this subject can be generated WITHOUT retrieval."""
    return _load(subject, family) is not None


def stats(subject: str, family: str = DEFAULT_FAMILY) -> dict:
    """Leaf/facet counts — for the corpus-health report and tests."""
    leaves = _load(subject, family)
    if not leaves:
        return {"total": 0}
    return {"total": len(leaves), "facets": len({l["facet"] for l in leaves})}


def _cooling_labels(subject: str, family: str, conn) -> set[str]:
    """Labels currently COOLING DOWN (used_ago IS NOT NULL).

    Note the inversion versus rag/sample.py: passages all exist as rows, so
    that module can ask "which rows are eligible". Leaves only get a row once
    they have been USED, so an untracked leaf is eligible by definition — the
    table records cooldown, not existence. Asking for the cooling set and
    subtracting is therefore correct where asking for the eligible set is not
    (that bug shipped and was caught in test: it returned only the 8 rows just
    marked used, making them the only candidates).

    Complexity: O(1) indexed query, returns at most (pool size) labels.
    """
    with conn.cursor() as cur:
        cur.execute("""SELECT label FROM taxonomy_leaf_reuse
                       WHERE subject=%s AND family=%s AND used_ago IS NOT NULL""",
                    (subject, family))
        return {r[0] for r in cur.fetchall()}


def _least_recently_used(subject: str, family: str, need: int, conn,
                         candidates: list[str]) -> list[str]:
    """Fallback when a subject's leaf pool is exhausted (all cooling down).

    Mirrors rag/sample.py's sections_for fallback: longest-cooling first, so a
    paper still gets its full count rather than coming up short.

    `candidates` is the set of labels STILL IN THE TAXONOMY FILE that were not
    already chosen. Filtering happens in SQL, not after the LIMIT, because the
    table can hold rows for leaves that no longer exist — a renamed or deleted
    leaf leaves its row behind. Post-filtering let those stale rows eat the
    LIMIT and then get discarded, so the caller came up short: measured
    2026-09-13 on a 74-leaf subject with 50 stale rows, a 12-question request
    delivered 4. There is no cleanup job for stale rows (a taxonomy edit is
    rare and a stray row is harmless), so this query must tolerate them.
    """
    if not candidates:
        return []
    with conn.cursor() as cur:
        cur.execute("""SELECT label FROM taxonomy_leaf_reuse
                       WHERE subject=%s AND family=%s AND label = ANY(%s)
                       ORDER BY used_ago DESC NULLS FIRST, RANDOM()
                       LIMIT %s""", (subject, family, candidates, need))
        return [r[0] for r in cur.fetchall()]


def leaves_for(subject: str, n: int, conn,
              family: str = DEFAULT_FAMILY) -> list[dict]:
    """Sample n distinct leaves, honouring cross-paper reuse cooldown.

    Eligible (not cooling down) leaves are preferred, same as rag/sample.py's
    sections_for. A subject with fewer than n eligible leaves — thin pool, or
    a long run of papers — is topped up from the least-recently-used ones
    rather than failing; the requested count is a promise. Logged, because
    that log line is the early signal a taxonomy needs more leaves.

    `conn` is REQUIRED here (unlike the old difficulty-only version) because
    reuse state lives in the DB, not the JSON file — this function cannot
    honour cooldown without a connection.

    Complexity: O(total leaves) for the eligibility set + O(1) fallback query.
    At ~470 leaves for the largest subject this is trivial per call.

    Returns [] when the subject has no taxonomy — caller falls back to RAG.
    """
    leaves = _load(subject, family)
    if not leaves:
        return []

    by_label = {l["label"]: l for l in leaves}
    # The taxonomy FILE is the source of truth for which leaves exist; the
    # table only says which are cooling down. So: every leaf, minus the
    # cooling set. A leaf with no row has never been used and is eligible.
    cooling = _cooling_labels(subject, family, conn)
    pool = [l for l in leaves if l["label"] not in cooling]

    random.shuffle(pool)
    chosen = pool[:n]

    if len(chosen) < n:
        need = n - len(chosen)
        picked = {l["label"] for l in chosen}
        # Candidates are leaves that EXIST in the file and are not already
        # chosen — passed into SQL so stale rows cannot consume the LIMIT.
        candidates = [l["label"] for l in leaves if l["label"] not in picked]
        fallback_labels = _least_recently_used(subject, family, need, conn, candidates)
        fallback = [by_label[lab] for lab in fallback_labels if lab in by_label]
        if len(chosen) + len(fallback) < n:
            logger.warning(
                "taxonomy[%s/%s]: only %d eligible leaves, need %d — "
                "taxonomy_data file may need expanding.",
                family, subject, len(chosen) + len(fallback), n)
        elif fallback:
            logger.info(
                "taxonomy[%s/%s]: %d leaves cooling down, topped up from "
                "least-recently-used.", family, subject, need)
        chosen += fallback

    return chosen


def sections_for(subject: str, n: int, conn,
                 family: str = DEFAULT_FAMILY) -> list[tuple[str, list]]:
    """sample.sections_for-shaped: [(leaf_label, [])].

    The empty passage list is the whole point — this is the no-RAG path.
    `conn` is required (reuse tracking needs it), matching sample.sections_for's
    own signature so generate.py's _sections_for can call either uniformly.
    """
    return [(l["label"], []) for l in leaves_for(subject, n, conn, family=family)]


def mark_used(subject: str, labels: list[str], conn,
             family: str = DEFAULT_FAMILY) -> None:
    """Mark these leaves as just-used (used_ago = 0), upserting new rows.

    Call ONCE per paper with every leaf that reached the model — mirrors
    rag/sample.py's mark_used exactly, including the "even if the question was
    later dropped" reasoning (the model still saw the topic; re-showing it
    would risk the same question on a retry).

    Complexity: one INSERT..ON CONFLICT per call (executemany), touching only
    the leaves just used — a few dozen rows at most.
    """
    if not labels:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO taxonomy_leaf_reuse (subject, family, label, used_ago, use_count)
               VALUES (%s, %s, %s, 0, 1)
               ON CONFLICT (subject, family, label)
               DO UPDATE SET used_ago = 0,
                             use_count = taxonomy_leaf_reuse.use_count + 1""",
            [(subject, family, lab) for lab in labels])
    conn.commit()


def advance_generation(family: str, conn) -> None:
    """Age every cooling-down leaf by one generation; free the expired.

    Call ONCE per paper, AFTER mark_used — same two-statement-not-one ordering
    as rag/sample.py's advance_generation, for the same reason: a leaf marked 0
    this run must not be immediately aged to 1 by the same call.

    Scoped by `family` only (not subject) so one call after a multi-subject
    paper ages every subject's leaves together — mirrors how a real paper
    spans subjects but is one generation event.

    Complexity: touches only rows with used_ago IS NOT NULL for this family —
    at most a few hundred, never the full leaf set.
    """
    with conn.cursor() as cur:
        cur.execute("""UPDATE taxonomy_leaf_reuse SET used_ago = used_ago + 1
                       WHERE family=%s AND used_ago IS NOT NULL""", (family,))
        cur.execute("""UPDATE taxonomy_leaf_reuse SET used_ago = NULL
                       WHERE family=%s AND used_ago > %s""",
                    (family, REUSE_COOLDOWN))
    conn.commit()
