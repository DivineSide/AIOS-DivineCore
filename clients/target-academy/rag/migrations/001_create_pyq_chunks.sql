-- pyq_chunks: stores Previous Year Question embeddings for the AI Generative pipeline.
-- Separate from book_chunks — PYQs are used to extract topic patterns (Phase 1),
-- not as the source material for question generation (that's book_chunks).
--
-- Run once in Supabase SQL editor before using POST /api/generate.

CREATE TABLE IF NOT EXISTS pyq_chunks (
    id          BIGSERIAL PRIMARY KEY,
    subject     TEXT NOT NULL,        -- matches book_chunks subject: uk-history, general-gk, etc.
    source_file TEXT NOT NULL,        -- filename of the source PYQ PDF/HTML
    chunk_text  TEXT NOT NULL,        -- one question (stem + options) as plain text
    embedding   vector(1536),         -- OpenAI text-embedding-3-small
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Fast subject filtering (used in pyq_lookup random fetch)
CREATE INDEX IF NOT EXISTS pyq_chunks_subject_idx ON pyq_chunks (subject);

-- NO ANN index on embedding — deliberately (dropped 2026-07-12).
-- The original ivfflat (lists=50) with pgvector's default probes=1 searched only
-- ~26 of 1,302 rows (~2% of the space): real 0.42-similarity matches never
-- surfaced and generation received ZERO style examples on every call. At this
-- row count an exact scan is <10ms with perfect recall; an approximate index is
-- pure accuracy loss with no speed win. Do not recreate below ~10k rows.
