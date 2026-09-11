# -*- coding: utf-8 -*-
"""tag_sections — assign each passage its authored book section.

Reads the .reocr transcript a book was ingested from, locates every markdown
heading, anchors each passage to its exact source offset, and writes the
nearest PRECEDING heading into book_passages.section.

Why this works (verified 2026-09-11 on uk-geography): passage text is canonical
— ingest.py's LLM returned sentence BOUNDARIES, never text — so a passage can
be found verbatim in the transcript. 209/210 anchored on a 150-char prefix.

Headings are NOT a chunk boundary in the current pipeline (ingest splits on
sentences, build_passages merges on char count), so a passage can straddle a
heading. It is assigned the heading its FIRST character falls under.

Usage:
    python rag/tag_sections.py --subject uk-geography --dry-run
    python rag/tag_sections.py --subject uk-geography
"""
import argparse, os, re, sys, unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2
from dotenv import load_dotenv

load_dotenv(BASE.parent / ".env")
load_dotenv(BASE.parent.parent / ".env")

REOCR = BASE / ".reocr"
ANCHOR = 150          # prefix length used to locate a passage in the source
MAX_HEAD = 90         # ignore "headings" longer than this — body text that ate a #


def norm(s: str) -> str:
    """NFC + whitespace collapse. Must match on both sides of the comparison."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip()


def load_headings(md: str) -> list[tuple[int, int, str]]:
    """(offset_in_normalised_text, level, title), in document order.

    Complexity: O(n*m) — norm() re-runs over the prefix per heading. n=#headings
    (~100), m=doc length (~450KB) so this is ~45M char ops per book, ~1s. Fine
    at this scale; if books get 10x bigger, track offsets incrementally instead.
    """
    out = []
    for m in re.finditer(r"^(#{1,4})\s*(.+)$", md, re.M):
        title = norm(m.group(2))
        if not title or len(title) > MAX_HEAD:
            continue
        out.append((len(norm(md[: m.start()])), len(m.group(1)), title))
    return out


def section_for(offset: int, heads: list[tuple[int, int, str]]) -> str | None:
    """Nearest preceding heading. O(log n) — heads is sorted by construction."""
    import bisect
    i = bisect.bisect_right([h[0] for h in heads], offset) - 1
    return heads[i][2] if i >= 0 else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=30)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT book_name FROM book_passages WHERE subject=%s", (a.subject,))
    books = [r[0] for r in cur.fetchall()]
    print(f"{a.subject}: {len(books)} book(s)")

    total = tagged = unmatched = 0
    for book in books:
        stem = Path(book).stem
        md_path = REOCR / f"{stem}.full.md"
        if not md_path.exists():
            print(f"  !! no transcript for {book} — skipped ({md_path.name})")
            continue
        src = md_path.read_text(encoding="utf-8")
        S = norm(src)
        heads = load_headings(src)

        cur.execute("""SELECT id, passage_text FROM book_passages
                       WHERE subject=%s AND book_name=%s ORDER BY (chunk_ids[1])""",
                    (a.subject, book))
        rows = cur.fetchall()
        print(f"  {book}: {len(rows)} passages, {len(heads)} headings")

        updates = []
        for pid, txt in rows:
            total += 1
            off = S.find(norm(txt)[:ANCHOR])
            if off < 0:
                unmatched += 1
                continue
            sec = section_for(off, heads)
            if sec:
                updates.append((sec, pid))
                tagged += 1

        if a.dry_run:
            seen, runs = None, []
            for sec, _ in updates:
                if runs and runs[-1][0] == sec:
                    runs[-1][1] += 1
                else:
                    runs.append([sec, 1])
            print(f"    -> {len(runs)} contiguous sections, "
                  f"{len({r[0] for r in runs})} distinct")
            for sec, n in runs[:25]:
                print(f"       n={n:3d}  {sec[:70]}")
        else:
            cur.executemany("UPDATE book_passages SET section=%s WHERE id=%s", updates)
            conn.commit()
            print(f"    -> wrote {len(updates)} rows")

    print(f"\ntotal={total} tagged={tagged} unmatched={unmatched}"
          f"{'  (DRY RUN — nothing written)' if a.dry_run else ''}")


main()
