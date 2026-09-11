# -*- coding: utf-8 -*-
"""sample — metadata-filtered passage sampling for generation.

Replaces query.py's embedding-based `passage_lookup` on the GENERATION path.
See rag/RAG_ROADMAP.md §4 for the full reasoning; briefly: we author the
"query" ourselves, so embeddings bridge a vocabulary gap that does not exist,
and cosine optimises precision@1 while paper generation needs coverage and
variety. Sampling is `WHERE subject = ? [AND section = ?] AND used_ago IS NULL
ORDER BY RANDOM()` — one indexed query, no API call.

Variety is DETERMINISTIC, not probabilistic: migration 007's `used_ago` marks a
passage as ineligible for REUSE_COOLDOWN generations after use. Random sampling
alone would still collide; the cooldown makes repeats impossible inside the
window.

Interface:
    sections_for(subject, n, conn)      -> [(section, [passage, ...]), ...]
    mark_used(passage_ids, conn)        -> None    (call once per paper)
    advance_generation(conn)            -> None    (call once per paper, after)

A "passage" dict is {"id", "text", "book", "section"} — the same "text" key
query.py returns, so downstream consumers are unchanged.
"""
from __future__ import annotations

import logging
import os
import random
from pathlib import Path

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent

# Generations a passage stays ineligible after use. 5 is a starting number —
# tune from Phoenix traces (RAG_ROADMAP §4). Higher = more variety but thin
# subjects exhaust sooner; uk-general-studies (267 passages, ~12 Q/paper) is
# the binding case.
REUSE_COOLDOWN = int(os.environ.get("RAG_REUSE_COOLDOWN", "5"))

# Passages per section handed to the model for ONE question. Sections are the
# book's own headings and average ~4 passages, so 2-3 is usually the whole
# section. More than this mostly adds tokens, not facts.
PASSAGES_PER_SECTION = int(os.environ.get("RAG_PASSAGES_PER_SECTION", "3"))


def _rows_to_passages(rows) -> list[dict]:
    return [{"id": r[0], "text": r[1], "book": r[2], "section": r[3]} for r in rows]


def sections_for(subject: str, n: int, conn) -> list[tuple[str, list[dict]]]:
    """Pick n distinct sections for `subject`, each with its sampled passages.

    Eligible (cooling-down-free) sections are preferred. If fewer than n exist
    — thin subject, or a long run of papers — the shortfall is filled by
    LEAST-RECENTLY-USED sections rather than failing: the requested count is a
    promise (see generate.py's top-up docstring). The fallback is logged
    because that log line is the early warning that a corpus needs expanding.

    Complexity: 2 indexed queries + 1 per chosen section = O(n) round trips.
    At n<=40 that is fine; if sections ever number in the thousands, fetch all
    candidate passages in ONE query with a window function instead of looping.

    Tradeoff: sampling sections first, then passages within them, keeps each
    question's context coherent (one authored topic). Sampling passages
    globally would be one query but would hand the model unrelated facts.
    """
    with conn.cursor() as cur:
        # Sections with at least one eligible passage.
        cur.execute("""
            SELECT section FROM book_passages
            WHERE subject = %s AND section IS NOT NULL AND used_ago IS NULL
            GROUP BY section
            ORDER BY RANDOM()
            LIMIT %s
        """, (subject, n))
        picked = [r[0] for r in cur.fetchall()]

        if len(picked) < n:
            need = n - len(picked)
            logger.warning(
                "sample[%s]: only %d eligible sections, need %d — falling back "
                "to least-recently-used for %d. Corpus may need expanding.",
                subject, len(picked), n, need)
            cur.execute("""
                SELECT section FROM book_passages
                WHERE subject = %s AND section IS NOT NULL
                  AND (%s = '{}' OR section <> ALL(%s))
                GROUP BY section
                ORDER BY MAX(COALESCE(used_ago, 0)) DESC, RANDOM()
                LIMIT %s
            """, (subject, picked, picked, need))
            picked += [r[0] for r in cur.fetchall()]

        out: list[tuple[str, list[dict]]] = []
        for sec in picked:
            # Eligible passages first; top up from the section if it is thin.
            cur.execute("""
                SELECT id, passage_text, book_name, section FROM book_passages
                WHERE subject = %s AND section = %s AND used_ago IS NULL
                ORDER BY RANDOM() LIMIT %s
            """, (subject, sec, PASSAGES_PER_SECTION))
            rows = cur.fetchall()
            if not rows:
                cur.execute("""
                    SELECT id, passage_text, book_name, section FROM book_passages
                    WHERE subject = %s AND section = %s
                    ORDER BY used_ago DESC NULLS FIRST, RANDOM() LIMIT %s
                """, (subject, sec, PASSAGES_PER_SECTION))
                rows = cur.fetchall()
            if rows:
                out.append((sec, _rows_to_passages(rows)))
    return out


def mark_used(passage_ids: list[int], conn) -> None:
    """Mark passages as just-used (used_ago = 0) and bump their lifetime count.

    Call ONCE per paper with every passage that reached the model — including
    ones whose question was later dropped, since the model still saw them and a
    repeat would produce the same question.
    """
    if not passage_ids:
        return
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE book_passages
            SET used_ago = 0, use_count = use_count + 1
            WHERE id = ANY(%s)
        """, (list(passage_ids),))
    conn.commit()


def advance_generation(conn) -> None:
    """Age every cooling-down passage by one generation; free the expired.

    Call ONCE per paper, AFTER mark_used. Two statements rather than one so a
    passage marked 0 this run is not immediately aged to 1 — order matters.

    Complexity: touches only rows with used_ago IS NOT NULL (a few hundred),
    not the full 19k table.
    """
    with conn.cursor() as cur:
        cur.execute("UPDATE book_passages SET used_ago = used_ago + 1 "
                    "WHERE used_ago IS NOT NULL")
        cur.execute("UPDATE book_passages SET used_ago = NULL "
                    "WHERE used_ago > %s", (REUSE_COOLDOWN,))
    conn.commit()
