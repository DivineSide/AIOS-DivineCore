-- 003: book_passages — the DERIVED, generation-grade view of book_chunks (2026-07-12).
--
-- WHY: the ingest chunker split on printed lines, so book_chunks holds one-fact
-- fragments (median 94-500 chars; ~4,900 rows under 100 chars are junk/headers).
-- A question generator needs multi-fact PASSAGES (distractors, सुमेलित pairs,
-- statement sets). Rebuilding chunks properly would mean re-running OCR +
-- segmentation; instead build_passages.py MERGES consecutive chunks of the same
-- book (document order = id order) into ~500-1200 char passages, drops junk,
-- and re-embeds. Only cost: embeddings (~$0.05).
--
-- RELATIONSHIP: book_chunks stays the canonical fine-grained store (used by
-- answer_from_rag marking, calibrated at that granularity). book_passages is a
-- rebuildable derived index — like a materialized view. chunk_ids keeps full
-- provenance; any passage can be traced back to its source chunks.
--
-- Rebuild any time with: python rag/build_passages.py --all --wipe

CREATE TABLE IF NOT EXISTS book_passages (
    id           BIGSERIAL PRIMARY KEY,
    book_name    TEXT NOT NULL,
    subject      TEXT NOT NULL,
    topic        TEXT,              -- distinct topic labels of merged chunks, " | "-joined
    passage_text TEXT NOT NULL,
    n_chunks     INT,               -- how many book_chunks merged into this passage
    chunk_ids    BIGINT[],          -- provenance -> book_chunks.id
    embedding    vector(1536),      -- text-embedding-3-small, same space as book_chunks
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS book_passages_subject_idx ON book_passages (subject);

-- Deliberately NO vector index: expected row count ~5-8k. Exact scan is <10ms
-- with perfect recall; an ivfflat here would repeat the pyq_chunks recall bug
-- (see 001 + .claude/checklists/database.md).
