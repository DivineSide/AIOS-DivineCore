-- 008: authored book section per passage (2026-09-11, PILOT).
--
-- WHY: generation-side retrieval is now metadata filtering + RANDOM() (see 007
-- and rag/RAG_ROADMAP.md §4). That needs a metadata column with real
-- selectivity, and the canonical syllabus does not provide one — the 2026
-- commission text compresses all of Uttarakhand history into ONE bullet, so
-- tagging against it would produce a constant column for uk-history/uk-culture.
--
-- The corpus is NOT thin — uk-history has 3,946 passages covering Katyuri
-- (254), Chand (790), Panwar (167), Gorkha (270), British rule (366),
-- statehood movement (101) and more. The granularity mismatch is in the
-- SYLLABUS text, not the books.
--
-- So the topic layer is taken from the BOOKS' OWN authored section headings,
-- syllabus-agnostic by design. Syllabus topics are then mapped ONTO these
-- sections in a separate, small mapping layer — so a syllabus revision means
-- rewriting ~8 mapping rows, not re-tagging thousands of passages.
--
-- SOURCE: rag/.reocr/<book>.full.md — the re-OCR'd markdown that ingest.py
-- consumed. It retains far more structure than survived chunking (geography:
-- 98 headings in the transcript vs 51 recoverable from passage text), because
-- ingest.py split on SENTENCES and build_passages.py merged on CHARACTER
-- COUNT — headings were never a boundary signal at either stage.
--
-- METHOD (verified before writing this migration, uk-geography book 1):
--   * passage text is CANONICAL — 192/210 verbatim in source, 17 differ only
--     by a duplicated fragment at an 8000-char window seam, 1 outlier. The
--     ingest LLM returned sentence BOUNDARIES, never text (see ingest.py's
--     SEGMENT_PROMPT: "Do NOT return sentence text").
--   * 209/210 passages anchor to an exact source offset by prefix match, so
--     "nearest preceding heading" is exact, not heuristic.
--
-- PILOT SCOPE: populated for uk-geography only. Nullable and additive — every
-- other subject stays NULL, no existing query is affected, and the whole thing
-- reverses with DROP COLUMN if the pilot is judged a failure.

ALTER TABLE book_passages
    ADD COLUMN IF NOT EXISTS section TEXT;

CREATE INDEX IF NOT EXISTS book_passages_section_idx
    ON book_passages (subject, section);

COMMENT ON COLUMN book_passages.section IS
    'Authored section heading from the source book, assigned by nearest preceding heading in the .reocr transcript. Syllabus-agnostic; syllabus topics map onto this separately.';
