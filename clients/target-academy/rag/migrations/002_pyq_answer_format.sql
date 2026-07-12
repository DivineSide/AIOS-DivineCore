-- 002: pyq_chunks gains the two fields the old parser threw away (2026-07-12).
--
--   answer — the paper's OFFICIAL answer letter (a-e), parsed from the
--            "Answer – (C)" lines present in every source markdown. Ground
--            truth for free; also lets style examples show correct answers.
--   format — mechanical question-format tag, for format-quota retrieval:
--            plain | match | assertion | statement | order | figure
--            (match = सुमेलित/सूची, assertion = अभिकथन-कारण,
--             statement = कथनों पर विचार, order = क्रम, figure = आकृति)
--
-- Run in Supabase SQL editor (or via psycopg2) BEFORE re-ingesting with the
-- format-aware parser. Both columns are nullable — old rows stay valid until
-- their source file is re-ingested.

ALTER TABLE pyq_chunks ADD COLUMN IF NOT EXISTS answer TEXT;
ALTER TABLE pyq_chunks ADD COLUMN IF NOT EXISTS format TEXT;

-- format-filtered retrieval ("give me 2 सुमेलित examples for this subject")
CREATE INDEX IF NOT EXISTS pyq_chunks_format_idx ON pyq_chunks (subject, format);
