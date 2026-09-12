# -*- coding: utf-8 -*-
"""backfill_pyq_format — tag `format` on pyq_chunks rows ingested before it existed.

WHY: 544 of 1,272 rows (42.8%) have format IS NULL — every one from a `.pdf`
source ingested before migration 002 added the column; every `.md` source is
100% tagged. blueprint.subject_format_mix() filters `WHERE format IS NOT NULL`,
so paper composition has been measured from 57% of the corpus, and the missing
43% is not a random sample — it is whole papers.

This re-runs ingest_pyq.detect_format() over chunk_text ALREADY IN THE DB. No
re-ingestion, no OCR, no Sarvam, no embeddings, no API cost — the text is
already there, only the derived column is missing.

`answer` is deliberately NOT backfilled: it is parsed from an "Answer – (X)"
line during segmentation, which is gone by the time text reaches the DB.
Recovering it needs real re-ingestion of those PDFs.

Usage:
    python rag/backfill_pyq_format.py --dry-run
    python rag/backfill_pyq_format.py
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2
from dotenv import load_dotenv

load_dotenv(BASE.parent / ".env")
load_dotenv(BASE.parent.parent / ".env")

# Reuse the ingest-time detector verbatim: the whole point is that backfilled
# rows are classified by the SAME rules as freshly ingested ones. Importing the
# module pulls its heavy deps (openai, anthropic clients) but constructs none —
# they are lazy — so this stays free.
from ingest_pyq import detect_format  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=30)
    cur = conn.cursor()
    cur.execute("""SELECT id, exam, source_file, chunk_text
                   FROM pyq_chunks WHERE format IS NULL ORDER BY id""")
    rows = cur.fetchall()
    print(f"{len(rows)} rows with format IS NULL\n")
    if not rows:
        return

    updates: list[tuple[str, int]] = []
    per_exam: dict[str, Counter] = {}
    samples: dict[str, tuple] = {}
    for pid, exam, src, text in rows:
        fmt = detect_format(text or "")
        updates.append((fmt, pid))
        per_exam.setdefault(exam or "?", Counter())[fmt] += 1
        if fmt != "plain" and fmt not in samples:
            samples[fmt] = (exam, src, " | ".join((text or "").splitlines())[:150])

    print("detected formats per exam:")
    for exam in sorted(per_exam):
        c = per_exam[exam]
        line = "  ".join(f"{f}={n}" for f, n in c.most_common())
        print(f"   {exam:30s} {line}")

    print("\none sample per non-plain format (spot-check the rules fired sanely):")
    for fmt, (exam, src, head) in sorted(samples.items()):
        print(f"   [{fmt:9s}] {exam}/{src[:34]}")
        print(f"               {head}...")

    total = Counter(f for f, _ in updates)
    print(f"\ntotal: {dict(total)}")

    if a.dry_run:
        print("\nDRY RUN — nothing written.")
        return

    # One round trip, not 544 (executemany against a remote DB is ~0.5s/row).
    from psycopg2.extras import execute_values
    execute_values(cur,
                   "UPDATE pyq_chunks AS p SET format = v.format "
                   "FROM (VALUES %s) AS v(format, id) WHERE p.id = v.id",
                   updates)
    conn.commit()
    print(f"\nwrote {len(updates)} rows")

    cur.execute("""SELECT format, count(*) FROM pyq_chunks
                   GROUP BY format ORDER BY 2 DESC""")
    print("\npyq_chunks format distribution now:")
    for f, n in cur.fetchall():
        print(f"   {str(f):12s} {n}")


main()
