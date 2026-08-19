-- 004: book_chunks becomes TEXT-ONLY — drop the chunk-level embedding column.
--
-- Why (2026-07-13): the Supabase free-plan DB hit 104% of its 0.5GB quota.
-- book_chunks carried 343MB, ~309MB of it TOAST-stored vectors that nothing
-- retrieves anymore: rag_lookup, passage_lookup and generation all search
-- book_passages (which owns its embeddings, built by build_passages.py).
-- book_chunks stays as the canonical TEXT source that passages are rebuilt
-- from — its vectors were pure dead weight.
--
-- Dropping the COLUMN (not just NULLing values) makes any straggler code that
-- still inserts chunk vectors fail loudly instead of silently re-bloating.
-- If chunk-level vectors are ever wanted again: re-add the column and re-embed
-- (text-embedding-3-small over the corpus ≈ ₹20).
--
-- NOTE: run VACUUM FULL book_chunks AFTER this (outside a transaction) to
-- actually reclaim the disk — DROP COLUMN alone only marks it dropped.

ALTER TABLE book_chunks DROP COLUMN IF EXISTS embedding;
