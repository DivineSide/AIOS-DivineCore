-- 005: parallel BGE-M3 embedding tables (2026-07-26).
--
-- WHY: OpenAI's text-embedding-3-small (1536-dim) is the current embedding
-- model for book_passages/pyq_chunks. OpenAI's account ran out of credits
-- (a real production outage, not hypothetical) and BGE-M3 (BAAI, open-weight,
-- multilingual, measurably stronger on Hindi retrieval per MIRACL/Hindi-BEIR
-- benchmarks than OpenAI's model) is being evaluated as a replacement.
--
-- BGE-M3 outputs 1024 dims, not 1536 — no free/open embedding model matches
-- OpenAI's 1536 exactly (checked: Jina v3 maxes at 1024, nomic-embed-text-v1.5
-- maxes at 768; there is no dimension-preserving swap). A schema change is
-- unavoidable if switching models.
--
-- SAFETY: the ORIGINAL book_passages/pyq_chunks tables are left COMPLETELY
-- UNTOUCHED by this migration — not even read. These are NEW, separate
-- tables. If BGE-M3 turns out worse, or OpenAI credits get topped up and the
-- team wants to revert, nothing was lost or overwritten; just keep using the
-- original tables (and query.py's provider switch, see EMBED_PROVIDER below,
-- flips back with zero data migration needed).
--
-- Populate via: python rag/reembed_bge.py --all (one-time, run locally —
-- BGE-M3 doesn't fit in the Hetzner VPS's RAM, confirmed via a live OOM test
-- 2026-07-25; this is a LOCAL, one-off job, not a server-side ingestion step).

CREATE TABLE IF NOT EXISTS book_passages_bge (
    id           BIGSERIAL PRIMARY KEY,
    source_id    BIGINT,            -- provenance -> book_passages.id (same source text)
    book_name    TEXT NOT NULL,
    subject      TEXT NOT NULL,
    topic        TEXT,
    passage_text TEXT NOT NULL,
    n_chunks     INT,
    chunk_ids    BIGINT[],
    embedding    vector(1024),      -- BAAI/bge-m3, NOT the same space as book_passages
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS book_passages_bge_subject_idx ON book_passages_bge (subject);

CREATE TABLE IF NOT EXISTS pyq_chunks_bge (
    id          BIGSERIAL PRIMARY KEY,
    source_id   BIGINT,             -- provenance -> pyq_chunks.id (same source text)
    subject     TEXT NOT NULL,
    source_file TEXT NOT NULL,
    chunk_text  TEXT NOT NULL,
    embedding   vector(1024),       -- BAAI/bge-m3, NOT the same space as pyq_chunks
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    answer      TEXT,
    format      TEXT,
    exam        TEXT
);

CREATE INDEX IF NOT EXISTS pyq_chunks_bge_subject_idx ON pyq_chunks_bge (subject);

-- Deliberately NO ANN/ivfflat index on either — same reasoning as the
-- original tables (see 001, 003): row counts here (~19k / ~1.3k) are small
-- enough that an exact scan is fast with perfect recall, and an approximate
-- index at this size is pure accuracy loss with no real speed win.
