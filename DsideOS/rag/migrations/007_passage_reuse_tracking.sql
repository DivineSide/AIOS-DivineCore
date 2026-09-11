-- 007: passage reuse tracking (2026-09-11).
--
-- WHY: cross-run variety was the round-2 audit's #1 finding. Two independent
-- papers shared ~4 of 6 sampled topics for uk-culture, because a 9-topic
-- syllabus pool plus DETERMINISTIC nearest-neighbour retrieval returns the
-- same passages for the same topic string every run (see DsideOS/CLAUDE.md,
-- "retrieval determinism is a feature until it's a bug").
--
-- The fix is not a smarter ranker. Generation-side retrieval is switching to
-- metadata filtering + RANDOM() sampling (we control the query, and there is
-- no single "best" passage for "write 4 geography questions" — cosine
-- optimises precision@1, which actively fights variety). Random sampling gives
-- probabilistic variety; this column makes it DETERMINISTIC: a passage used
-- recently is simply not eligible.
--
-- MECHANIC — used_ago is an AGE IN GENERATIONS, not a timestamp:
--     0        used in the most recent run
--     1..5     used that many runs ago, still cooling down
--     NULL     eligible
-- After each run: set 0 on the passages just used, increment every non-null
-- value, then clear anything past REUSE_COOLDOWN (5). A wall-clock timestamp
-- was rejected because "last 5 papers" must not drift with how often papers
-- are generated.
--
-- EXHAUSTION: thin subjects (uk-general-studies has 267 passages, ~12
-- questions/paper) will run out of eligible rows. Selection then falls back to
-- ORDER BY used_ago DESC (least-recently-used first) rather than failing —
-- the requested count stays a promise. The fallback is logged so Phoenix shows
-- which subject is running thin, i.e. which corpus needs expanding.
--
-- COST: the post-run increment is a single UPDATE touching only non-null rows
-- (a few hundred), not the full 19k table.

ALTER TABLE book_passages
    ADD COLUMN IF NOT EXISTS used_ago  SMALLINT,          -- NULL = eligible
    ADD COLUMN IF NOT EXISTS use_count INTEGER NOT NULL DEFAULT 0;

-- Selection always filters subject + eligibility, so index the pair.
-- Partial index: only eligible rows are ever scanned by the hot path.
CREATE INDEX IF NOT EXISTS book_passages_eligible_idx
    ON book_passages (subject)
    WHERE used_ago IS NULL;

-- The fallback path (exhausted subject) orders by used_ago within a subject.
CREATE INDEX IF NOT EXISTS book_passages_used_ago_idx
    ON book_passages (subject, used_ago);

COMMENT ON COLUMN book_passages.used_ago IS
    'Generations since this passage was last used in a paper; NULL = eligible. Cleared past REUSE_COOLDOWN.';
COMMENT ON COLUMN book_passages.use_count IS
    'Lifetime count of papers that used this passage. Diagnostic only — never gates selection.';
