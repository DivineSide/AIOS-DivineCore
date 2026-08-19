# DsideOS — Project Context

## Where this sits

DivineSide is an early-stage SaaS startup, not yet a proven product company —
this repo is its first real product, not a research platform. **DsideOS** is
the backend for a content pipeline + AI question-generation system, built
first for one paying client (**Target Academy**, a UKSSSC exam-prep coaching
institute) and generalized as real patterns proved out, not designed ahead of
need. `pipeline/`, `rag/`, and `corpus/` live in this repo because they turned
out to be genuinely client-agnostic; anything still specific to Target
Academy's own branding/assets/workflow stays under `clients/target-academy/`
(see `.overview.md` for the exact split and why).

See the repo-root `CLAUDE.md` for the full company/team/business context.
This file covers only what's specific to working in `DsideOS/`.

## What this repo actually does

Two things, both live in production for Target Academy:

1. **Format-agnostic content pipeline** — any input (docx/pdf/scanned/photo)
   → universal Unicode questions JSON → branded paper/deck/answer-key/solution
   in the client's exact template. See `.overview.md` for the full API shape.
2. **RAG-based exam-question generation** — a corpus of ingested textbooks +
   real past-year-question papers, retrieved and used to generate new,
   grounded exam questions on demand (`worker/generate.py`, `rag/query.py`).

## Working notes carried over from real production incidents

These aren't abstract best practices — each one maps to a real bug found and
fixed in this system. Read them as "why this matters here," not generic advice.

**Retrieval determinism is a feature until it's a bug.** `rag/query.py`'s
searches are a pure deterministic nearest-neighbor scan — same query, same
top-k, every time. That's correct for grounding (you want the single best
match for a fact), but it means two separate generation runs asking about the
same syllabus topic will draw the identical passage and produce near-identical
questions. Cross-run variety and grounding precision pull in opposite
directions on the SAME retrieval call — don't try to fix one by weakening the
other (e.g. don't randomize top-k to get variety; that just produces wrong
answers on a different schedule). Fix variety at the topic-selection layer or
via passage-reuse tracking, not by making retrieval fuzzier.

**Grounding needs real sentences to quote, not just "relevant" text.** The
strict grounding gate (`worker/ground.py`) rejects any generated question
whose fact isn't literally quotable from a retrieved passage. This is right,
but it means the CORPUS SHAPE matters more than the embedding model: a
raw MCQ-question-dump or a rule+example table has no standalone quotable
sentence for the gate to match against, even when the fact is "in there"
semantically. Subjects with thin/badly-shaped source material (this
system's `hindi`/`computer`) need restructuring at ingestion, not a smarter
retrieval query.

**Document quality has to be scored, not assumed.** `rag/query.py`'s
`_garble_score()` exists because some source books survived OCR/digitization
badly (repeated-conjunct garbage, corrupted digits) and some didn't — scoring
candidates and preferring the cleaner ones (never rejecting outright, since
thin retrieval beats none) fixed more real generation failures than any
embedding/model upgrade did. Same lesson independently confirmed by an
outside enterprise-RAG engineer's write-up: "document quality detection" was
their single highest-ROI fix too, ahead of chunking or embedding choices.

**Hybrid retrieval (dense + lexical) recovers what pure semantic search
misses.** `RAG_HYBRID`/`_hybrid_search` in `rag/query.py` fuses cosine
similarity with Postgres full-text rank via Reciprocal Rank Fusion — added
because dense-only retrieval blurs exactly the tokens a fact hinges on (a
specific year, a proper noun, an exam-code acronym). Don't assume a bigger
or better embedding model fixes this; the failure mode is structural
(semantic search finds MEANING, not exact tokens), so a lexical channel is a
different fix, not a redundant one.

**Metadata/exact-match filters aren't optional even with good embeddings.**
`subject`/`exam`/`format` columns on `pyq_chunks`/`book_passages` are hard
`WHERE` filters applied before/alongside the vector search, not just
metadata for display. A vdo-vpdo paper's match-question style examples must
come from vdo-vpdo's own real papers, not semantically-similar examples from
a different exam with a different real format mix — semantic similarity
alone doesn't know about that boundary.

**Query rewriting before embedding is live, not hypothetical.** `RAG_HYDE`
(on by default, see `.env.example`) embeds a hypothetical answer sentence
instead of the raw topic — a plausible answer sits closer to real source
passages in vector space than a bare question/topic string does. This is
HyDE, already shipped; don't re-propose it as a future improvement.

**Not-yet-covered gaps worth knowing about, not urgent today**:

- **No reranking stage.** Retrieval today is dense (bi-encoder) + lexical,
  fused by RRF — there's no second-pass cross-encoder or LLM reranker
  scoring the shortlist before it's used. Fine at the current corpus size
  (exact scan, no ANN index below ~10k rows per subject, see migration
  notes), but worth reconsidering if a subject's corpus grows enough that
  the first-pass shortlist quality becomes the bottleneck.
- **No structured evaluation harness.** Threshold tuning (topic-dedup
  cosine cutoffs, garble scoring, grounding checks) has so far been done
  by hand — a real example pair, a measured number, a judgment call — not
  against a saved eval set or automated metrics (precision/recall,
  RAGAS-style faithfulness scoring). This works at today's scale but means
  no regression detection when something changes; worth a real eval set
  before the corpus/subject count grows much further.
- **No temporal tagging or cross-reference metadata.** `subject`/`exam`/
  `format` are real hard-filter metadata (see above), but nothing tracks
  *when* a passage's content is valid (a stale fact retrieved as if
  current) or links related-but-not-similar passages (e.g. an appointment
  linked to the event that caused it). Not yet hit as a real bug here.
- Acronym disambiguation (a token meaning two different things in two
  different subjects — not yet hit here, but plausible as corpus grows),
  full table/structured-data handling (most PYQ/book content here is
  prose, not dense tables, so this hasn't bitten yet), and self-hosted-model
  infrastructure tradeoffs (explored once for embeddings, deferred — see
  the parallel `_bge`/`_e5` migration files in `rag/migrations/` for that
  abandoned exploration's residue, not yet cleaned up).

## Reading this codebase

Start with `.overview.md` (stack, API shape, deploy flow) and each folder's
own `.abstract.md`/`.overview.md` before diving into files — this repo
follows the tiered-context convention documented in the root `CLAUDE.md`.
