# RAG System — Accumulated Learnings

Reference document for design discussions on the DSideOS RAG pipeline.
Consult this before designing or modifying ingestion, retrieval, or
evaluation stages — per the "designing something new" rule, this is
context, not a substitute for laying out options before implementing.

---

## 1. Ingestion & Data Quality

Edge cases — broken PDFs, unexpected formats, inconsistent structure —
consume the most time in the ingestion stage, more than the "clean path"
ever does. They require careful manual scrutiny; getting them wrong means
a full rerun of ingestion on the affected files, not a quick patch.

Treat ingestion as the stage most likely to hide silent failures. Flag,
don't skip, files that fail to parse cleanly — a dropped or malformed
document is worse than a slow ingestion run, because it fails silently
downstream at retrieval time instead of failing loudly at ingestion time.

## 2. Metadata Architecture

Metadata — structured facts about a chunk stored alongside its embedding,
not embedded into the vector itself — meaningfully improves retrieval
quality. Three components, in order of general value:

- **Classification schema** — a fixed, decided-in-advance taxonomy every
  chunk is tagged with (subject, topic, category). Don't invent categories
  ad hoc per chunk; decide the schema upfront and tag consistently.
- **Temporal tagging** — the time period a chunk's content refers to,
  separate from when it was retrieved or ingested. Prevents an old source
  describing something as "current" from being retrieved as if it answers
  a present-day question.
- **Cross-references** — explicit links between chunks that are related in
  reality but not similar enough in wording for vector search to connect
  them automatically (e.g. a governor's appointment linked to the war that
  preceded it).

Designing the right schema is the slow part, not implementing it — the
schema itself is quick to write down once the actual shape of the data
(including its duplication and inconsistency) is understood.

## 3. Query Parsing / Query Optimization

How the user's raw prompt gets transformed before retrieval materially
affects retrieval quality. Two techniques worth applying:

- **LLM query rewriter** — pass the user's raw question through an LLM
  first to reformulate it into a clearer, more retrieval-friendly form
  before embedding it. Fixes ambiguous phrasing, expands shorthand,
  resolves referents that a raw user query wouldn't retrieve well against.
- **HyDE (Hypothetical Document Embeddings)** — instead of embedding the
  raw question, first ask an LLM to generate a hypothetical *answer* to
  the question, then embed that hypothetical answer and search with it.
  Works because a plausible answer is semantically closer to real source
  chunks than a raw question is — questions and answers don't always sit
  close together in vector space, even when the answer is correct.

Query parsing is a cheap, high-leverage stage to optimize relative to its
cost — it happens once per query, before the expensive retrieval and
reranking stages.

## 4. Retrieval Architecture — Bi-Encoder + Cross-Encoder Reranking

Two-stage design, standard pattern for combining a cheap-but-approximate
method with an expensive-but-precise one:

- **Stage 1 — Bi-encoder + pgvector/HNSW.** Question and chunk are
  encoded independently into vectors; chunks are pre-computed once ahead
  of time. Fast (O(log n) via HNSW indexing), scales to the full corpus,
  but loses cross-text nuance because the model never sees question and
  chunk together. Returns a shortlist (top 20-50) from the full corpus.
- **Stage 2 — Cross-encoder reranking.** Question and each shortlisted
  chunk are fed into the model together, producing a true relevance
  score. More accurate — captures cross-text relationships bi-encoders
  structurally cannot — but O(n) per query, so only ever run on the small
  shortlist from stage 1, never the full corpus.

Never run a cross-encoder (or an LLM-based reranker) against the full
corpus directly — the cost scales linearly with corpus size and stage 1
exists specifically to avoid that. Two reranker options for stage 2:

- **Cross-encoder model** (e.g. `ms-marco-MiniLM`, Cohere rerank) — cheap
  per call, purpose-built for relevance scoring, good default.
- **LLM-based reranker** — ask an LLM directly to rank or score candidates.
  More expensive and slower per call, but more reasoning ability on
  genuinely ambiguous relevance judgments. Use selectively, not as default.

## 5. Evaluation

Historically the most undervalued part of RAG development — easy to skip
in favor of shipping, expensive to skip in terms of silent quality
degradation. Two core retrieval metrics:

- **Precision** — of the chunks retrieved, how many were actually
  relevant. Low precision = noisy context reaching the LLM.
- **Recall** — of all truly relevant chunks in the corpus, how many were
  actually retrieved. Low recall = the right answer exists but never
  reached the LLM at all.

These trade off against each other and both need tracking — high
precision with low recall means clean but incomplete context; high recall
with low precision means the right chunk is buried in noise.

**Tools:**

- **RAGAS** — an evaluation framework built specifically for RAG
  pipelines. Computes metrics like faithfulness (does the answer stay
  grounded in retrieved context, or hallucinate beyond it), answer
  relevancy, and context precision/recall automatically against a test
  set, rather than requiring manual grading of every output.
- **Phoenix (Arize)** — open-source LLM observability and tracing.
  Captures each pipeline stage's input/output (embed → retrieve → rerank
  → generate) individually, enabling debugging of exactly which stage
  failed on a bad response, and supports experimentation — comparing
  pipeline changes against a saved evaluation set with real numbers
  rather than manual spot-checking.

**Workflow this enables:** use monitoring/eval tooling to identify
specific weak areas in the pipeline first — which stage, which query
type, which document category is underperforming — then work backwards
from that diagnosis to fix the specific weak point, rather than making
broad changes without a diagnosis. Comprehensive evaluation before
directed fixing, not the reverse.

## 6. Supplementary — Diagrams and Images

- Use **code-based generation** (e.g. Mermaid, Graphviz, matplotlib) for
  diagrams — precise, reproducible, versionable alongside code.
- Use **diffusion models** for illustrative/organic images where precision
  isn't the goal and photographic or artistic quality is.