-- 006: parallel multilingual-e5-base embedding tables (2026-07-26).
--
-- WHY: alongside the BGE-M3 parallel tables (005), multilingual-e5-base
-- (intfloat/multilingual-e5-base, 278M params, ~1.1GB RAM) is being evaluated
-- as a smaller, Hetzner-self-hostable alternative to both OpenAI's
-- text-embedding-3-small (currently account-exhausted, a real outage) and
-- BGE-M3 (confirmed too large to self-host on the CX23 VPS, OOM-killed in a
-- live test). e5-base outputs 768 dims — a THIRD dimension alongside 1536
-- (OpenAI) and 1024 (BGE-M3), so a third parallel table set is needed.
--
-- SAFETY: same pattern as 005 — the ORIGINAL book_passages/pyq_chunks tables,
-- and the BGE parallel tables, are left COMPLETELY UNTOUCHED. These are new,
-- separate tables only. Nothing is lost if e5-base doesn't pan out.
--
-- Populate via: python rag/reembed_e5.py --all (one-time, run locally —
-- small enough to embed on a laptop CPU in a single pass).

CREATE TABLE IF NOT EXISTS book_passages_e5 (
    id           BIGSERIAL PRIMARY KEY,
    source_id    BIGINT,            -- provenance -> book_passages.id (same source text)
    book_name    TEXT NOT NULL,
    subject      TEXT NOT NULL,
    topic        TEXT,
    passage_text TEXT NOT NULL,
    n_chunks     INT,
    chunk_ids    BIGINT[],
    embedding    vector(768),       -- intfloat/multilingual-e5-base, NOT the same space as book_passages/_bge
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS book_passages_e5_subject_idx ON book_passages_e5 (subject);

CREATE TABLE IF NOT EXISTS pyq_chunks_e5 (
    id          BIGSERIAL PRIMARY KEY,
    source_id   BIGINT,             -- provenance -> pyq_chunks.id (same source text)
    subject     TEXT NOT NULL,
    source_file TEXT NOT NULL,
    chunk_text  TEXT NOT NULL,
    embedding   vector(768),        -- intfloat/multilingual-e5-base, NOT the same space as pyq_chunks/_bge
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    answer      TEXT,
    format      TEXT,
    exam        TEXT
);

CREATE INDEX IF NOT EXISTS pyq_chunks_e5_subject_idx ON pyq_chunks_e5 (subject);

-- Deliberately NO ANN/ivfflat index — same reasoning as 001/003/005: row
-- counts here (~19k / ~1.3k) are small enough that an exact scan is fast
-- with perfect recall.
