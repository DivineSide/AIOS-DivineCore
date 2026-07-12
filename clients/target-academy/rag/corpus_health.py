# -*- coding: utf-8 -*-
"""
corpus_health — per-book damage report for the RAG corpus. Run after ANY ingest.

Turns "who knows how many areas have this mistake?" into a one-command answer.
All detectors are deterministic code (zero LLM cost). Each detector targets a
corruption class we have actually observed in production:

  year-digit   Tesseract reads printed '1' as '4' -> reign years like (4625-4638),
               "4790 में". FACT-level damage: a generated question grounded on it
               confidently teaches a wrong year. Found 2026-07-12 in 3 scanned
               uk-history books (~600 chunks).
  matra-garble Tesseract collapses conjuncts to ि -> इततहास, पंिार िंश.
               SPELLING-level damage: models read through it, but verbatim
               echoes look unprofessional.
  fragment     chunks under 100 chars — page headers/stray lines that pollute
               retrieval slots (the chunker's line-split legacy).
  html-junk    raw <td>/<tr> table markup that leaked into text.

Usage:
    python corpus_health.py                # report on book_chunks + pyq_chunks
    python corpus_health.py --table book_passages
Exit code is 0 always — this reports, humans decide.
"""

import argparse
import io
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)

import psycopg2
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]


def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return


_load_env()

# Detector SQL fragments, per text column. Regexes are POSIX (Postgres ~).
_DETECTORS = {
    # a 4-9xxx "year" in a year context, or a (dddd-dddd) range starting 4-9:
    # impossible as dates; peak elevations etc. don't appear in these contexts.
    "year_digit": (r"{col} ~ '\m[4-9][0-9]{{3}}\M\s*(में|ई|तक|से)'"
                   r" OR {col} ~ '\(\s*[0-9]{{3,4}}\s*[-–]\s*[4-9][0-9]{{3}}\s*\)'"),
    # signature Tesseract conjunct-collapse tokens observed in this corpus
    "matra_garble": (r"{col} ~ '(इततहास|पंिार|िंश|ऐततहालसक|राजिंश|स्ितंत्र|प्रलसद्ध)'"),
    "fragment": r"length({col}) < 100",
    "html_junk": r"{col} LIKE '%<td>%' OR {col} LIKE '%<tr>%'",
}

_TABLES = {
    "book_chunks":   ("book_name",   "chunk_text"),
    "book_passages": ("book_name",   "passage_text"),
    "pyq_chunks":    ("source_file", "chunk_text"),
}


def report(conn, table: str):
    group_col, text_col = _TABLES[table]
    dets = {k: v.format(col=text_col) for k, v in _DETECTORS.items()}
    sel = ",\n  ".join(
        f"count(*) FILTER (WHERE {cond}) AS {name}" for name, cond in dets.items()
    )
    sql = (f"SELECT {group_col}, count(*) AS total,\n  {sel}\n"
           f"FROM {table} GROUP BY {group_col} ORDER BY 3 DESC, 4 DESC, 2 DESC")
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    print(f"\n=== {table} ===")
    hdr = f"{'source':48} {'total':>6} {'yr-dig':>7} {'matra':>6} {'frag':>6} {'html':>5}"
    print(hdr)
    print("-" * len(hdr))
    flagged = 0
    for name, total, yd, mg, fr, hj in rows:
        # a source is UNHEALTHY when fact-level or spelling damage exceeds 2%,
        # or fragments exceed 40% (retrieval pollution)
        bad = (yd + mg) / max(total, 1) > 0.02 or fr / max(total, 1) > 0.40
        mark = "  <<< " if bad else ""
        flagged += bad
        print(f"{str(name)[:47]:48} {total:6} {yd:7} {mg:6} {fr:6} {hj:5}{mark}")
    print(f"\n{len(rows)} sources, {flagged} flagged unhealthy (<<<).")


def main():
    ap = argparse.ArgumentParser(description="Deterministic corpus damage report.")
    ap.add_argument("--table", choices=list(_TABLES), default=None,
                    help="one table only (default: book_chunks + pyq_chunks + book_passages)")
    args = ap.parse_args()

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=30)
    tables = [args.table] if args.table else list(_TABLES)
    for t in tables:
        try:
            report(conn, t)
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            print(f"\n=== {t} === (table does not exist yet — skipped)")
    conn.close()


if __name__ == "__main__":
    main()
