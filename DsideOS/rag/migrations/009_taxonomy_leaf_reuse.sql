-- 009: taxonomy leaf reuse tracking (2026-09-13).
--
-- WHY: the no-RAG path (worker/taxonomy.py, Phase 2) samples question-sized
-- syllabus leaves instead of book passages, but had NO cross-paper memory —
-- every call drew fresh from the whole pool, so two consecutive papers on a
-- ~120-leaf subject (uk-culture) had real collision odds. This mirrors
-- migration 007's passage cooldown exactly, applied to leaves instead of rows:
-- same used_ago/use_count mechanic, same REUSE_COOLDOWN=5, same age-in-
-- generations (not wall-clock) reasoning — see 007's own comment for why.
--
-- WHY A SEPARATE TABLE, NOT A COLUMN ON book_passages: leaves are not corpus
-- rows. They live in worker/taxonomy_data/<family>/<subject>.json, authored text
-- with no existing table row to attach a column to. A leaf is identified by
-- (subject, label) — a string key, not an integer id like book_passages.id —
-- because the taxonomy file is the source of truth for WHICH leaves exist;
-- this table only tracks WHEN each one was last used.
--
-- CONSEQUENCE OF THE STRING KEY: editing a leaf's label in the taxonomy JSON
-- is indistinguishable from deleting one leaf and adding another — its reuse
-- history resets to eligible. Harmless (a cold start, not a corruption), but
-- worth knowing before renaming leaves for cosmetic reasons.
--
-- MECHANIC (identical to 007):
--     used_ago  NULL      = eligible
--               0         = used in the most recent run
--               1..5      = used that many runs ago, still cooling down
-- After each run: set 0 on leaves just used, increment every non-null value
-- across ALL subjects, then clear anything past REUSE_COOLDOWN (5).
--
-- SCOPE: (subject, family) together, not just subject — a future non-UKSSSC
-- syllabus family reusing a subject name (unlikely today, but taxonomy.py's
-- own `family` parameter already anticipates it) must not share cooldown
-- state with an unrelated syllabus's leaves of the same name.

CREATE TABLE IF NOT EXISTS taxonomy_leaf_reuse (
    subject   TEXT        NOT NULL,
    family    TEXT        NOT NULL DEFAULT 'uksssc-master',
    label     TEXT        NOT NULL,
    used_ago  SMALLINT,                       -- NULL = eligible
    use_count INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (subject, family, label)
);

-- Selection always filters (subject, family) + eligibility.
CREATE INDEX IF NOT EXISTS taxonomy_leaf_reuse_eligible_idx
    ON taxonomy_leaf_reuse (subject, family)
    WHERE used_ago IS NULL;

-- Fallback path (subject exhausted) orders by used_ago within (subject, family).
CREATE INDEX IF NOT EXISTS taxonomy_leaf_reuse_used_ago_idx
    ON taxonomy_leaf_reuse (subject, family, used_ago);

COMMENT ON TABLE taxonomy_leaf_reuse IS
    'Cross-paper reuse cooldown for no-RAG taxonomy leaves (worker/taxonomy.py). Mirrors book_passages.used_ago/use_count (migration 007) but keyed by (subject, family, label) since leaves are authored text, not corpus rows.';
COMMENT ON COLUMN taxonomy_leaf_reuse.used_ago IS
    'Generations since this leaf was last used in a paper; NULL = eligible. Cleared past REUSE_COOLDOWN (5, same constant as passage reuse).';
COMMENT ON COLUMN taxonomy_leaf_reuse.use_count IS
    'Lifetime count of papers that used this leaf. Diagnostic only — never gates selection.';
