# RAG Build Roadmap

Tracks the production-RAG checklist for DsideOS, one stage at a time.
Each section fills in as that stage is audited/built/tuned — status,
what's live, what's missing, decisions made. Blank sections below are
not-yet-covered, not skipped.

See also: [rag_learnings.md](../rag_learnings.md) (general RAG theory
reference) and `DsideOS/CLAUDE.md` (accumulated production incidents).

---

## 1. Chunking

Status: not yet audited

## 2. Ingestion Quality Scoring

Status: not yet audited

## 3. Embedding Model

Status: not yet audited

## 4. Search + Metadata Filtering

Status: REDESIGNED 2026-09-11 — semantic search dropped from the generation path

**The decision: no query-time semantic search.** Retrieval becomes metadata
filtering + `ORDER BY RANDOM()`, with reuse tracking for variety.

**Why semantic search doesn't earn its place here** (Mayank's call, and the
reasoning holds):
- Embeddings exist to bridge vocabulary mismatch between an UNPREDICTABLE user
  query and a corpus. We have no unpredictable query — the "query" is a syllabus
  string we wrote, matched against a corpus we ingested. Embedding both sides to
  rediscover a relationship known at ingestion time is expensive redundancy.
- There is no single correct answer to "give me material for 4 geography
  questions." Cosine optimises **precision@1**; we need **coverage and variety**.
  Ranking by similarity actively fights the goal — same string in, same top-k
  out, every run. That IS the determinism-vs-variety tension in CLAUDE.md, and
  it turns out to be a wrong-tool problem, not a real tradeoff.
- Accidental evidence: `PASSAGE_THRESHOLD = 0.20` has been INERT in production
  the whole time (`_hybrid_search` accepts `threshold` and never uses it — dense
  returns cosine ~0.42-0.52, hybrid returns RRF scores ~0.03 into the same
  field). Papers shipped anyway. Cosine ranking was not doing the work we
  assumed.

**Where embeddings still earn their cost: ingestion, not query time.** Same
tool, the job it's actually good at — one-time structure building, never
per-question.

**Subtopics: considered and rejected** (2026-09-11). Clustering uk-geography's
385 passages produced genuinely coherent groups (dams/irrigation, rivers/lakes,
forests, migration, biodiversity) at zero API cost. But subtopics buy only
PROBABILISTIC variety, while reuse tracking gives DETERMINISTIC variety — and
invented subtopic names are not canonical, not checkable against any authority,
and become maintenance debt as the corpus grows. Reuse tracking supersedes them.

**Also rejected: whole-topic mega-chunks.** Tempting (one chunk = one topic) but
(a) token waste — most of a large chunk goes unused per question, (b) the model
self-selects the FAMOUS facts from a big blob every run, moving the variety
problem from retrieval to generation where the priors are stronger, and (c)
grounding degrades — the judge must find a verbatim quote in a much bigger
haystack. Passages stay ~1,200 chars; structure goes in metadata, not chunk size.

**Shipped:** `rag/migrations/007_passage_reuse_tracking.sql` (applied
2026-09-11). Adds `used_ago SMALLINT` (generations since use, NULL = eligible,
cooldown 5) and `use_count INTEGER` (diagnostic) to `book_passages`, plus a
PARTIAL index on `(subject) WHERE used_ago IS NULL` so the hot path is an index
scan. Verified: planner uses it, cost 3.45, all 19,182 rows start eligible.
Cooldown of 5 is a starting number — tune from Phoenix traces.

Exhaustion fallback: when a subject has too few eligible rows, order by
`used_ago DESC` (least-recently-used) instead of failing, and LOG it — that log
line is the early warning that a corpus needs expanding.

**Still to build:**
1. `syllabus_topic` column — tag every passage with its canonical syllabus topic
   (the metadata that makes filtering actually selective; see §Chunking note)
2. `sample_passages(subject, topic, n)` — eligible-first query with LRU fallback
3. Post-run bookkeeping — mark used (0) → increment non-nulls → clear past 5
4. Replace `passage_lookup()` in `generate.py` with the above

## 5. Retrieval Fusion

Status: OBSOLETE for the generation path (2026-09-11)

RRF fusion of dense + lexical was solving a ranking problem that no longer
exists — see §4, generation-side retrieval is metadata + RANDOM(). The
`RAG_HYBRID` machinery in `rag/query.py` stays for any future query-driven
surface (a student-facing search, say), but it is off the generation path.

## 6. Reranking

Status: not yet audited

## 7. Query Parsing

Status: not yet audited

## 8. LLM Choice

Status: in progress — free-tier drafting model picked, paid candidates parked for later

**Current pick (drafting): `openai/gpt-oss-120b` via Groq, free tier.**
- Why: Sarvam-105b hit a real ~7x price hike (2026-08-05) and this project has
  no budget for it right now. `gpt-oss-120b` is Apache 2.0, MoE (117B total /
  5.1B active), free on Groq (30 req/min, 1,000 req/day, no card).
- Real evidence, not marketing: OpenAI's own model card reports MMMLU Hindi =
  82.2 (competitive with o4-mini's 85.9). An independent Hindi-benchmark paper
  (arXiv 2508.19831) has it topping >20B models on **IFEval-Hi** — the "follows
  instructions in Hindi" axis, directly the failure mode that killed
  Sarvam-30b (86% of drops were one broken instruction, not a knowledge gap).
  Paper's own caveat: reasoning mode may inflate its score; treat as
  directional, not conclusive.
- `reasoning_effort` (low/medium/high) is a real, documented Groq API param
  for this model — unlike `qwen/qwen3.6-27b`, which we live-tested on Groq
  2026-08-24 and it burned its whole token budget on English chain-of-thought
  and never produced the requested Hindi output (same failure class as
  Sarvam-30b). gpt-oss's reasoning is dial-able, not a dead end.
- `gpt-oss-20b` (same family, smaller/faster) is the fallback if 120b's rate
  limit becomes a bottleneck.
- Not yet done: wiring this into `_gen_slot`'s draft call as a
  `GEN_PROVIDER=groq` branch, and running a real batch through
  `validate_gen.py` + `ground.py` to measure actual drop/retry rate — the
  same test discipline that caught Sarvam-30b's problem, not a benchmark
  paper's word for it alone.

**Parked for later (revisit once there's budget) — verified live + priced
2026-08-24, but cost real money:**
- **Qwen3-32B** — Apache 2.0, cheapest verified paid option ($0.08/$0.28 per
  1M on DeepInfra). Highest real Hindi-instruction score found anywhere in
  this search: IndicIFEval-Trans Hindi = 78.5% (arXiv 2602.22125). NOT the
  same model as `qwen/qwen3.6-27b` on Groq — that's a newer, different-sized,
  untested-on-Hindi generation; don't conflate the two.
- **Llama-4 Scout** — Meta Community License (not Apache/MIT — real
  attribution/field-of-use terms, flag for review before production).
  IndicIFEval-Trans Hindi = 77.3%, near-identical to Qwen3-32B. Biggest
  context window of any candidate (10M tokens) — most relevant if/when we
  move to generating multiple questions per model call (see note below).
  Live via OpenRouter/DeepInfra (~$0.10/$0.30 per 1M); confirmed NOT live on
  Groq anymore (404'd on a real key, 2026-08-24 — Groq's own deprecation docs
  were right, OpenRouter's routing table was stale).
- **Sarvam-105b** — now open-weight itself (Apache 2.0, HuggingFace
  `sarvamai/sarvam-105b`, released 2026-02) — the exact model already proven
  in this pipeline. But still only callable through Sarvam's own paid API
  (no third-party host has picked it up yet); real cost, same single-vendor
  risk as before, just at ~7x the old price.
- **DeepSeek V4-Flash/Pro** — cheap, MIT, but zero published Hindi evidence
  found anywhere — would be a genuine bet, not a data-backed pick. Our
  `DEEPSEEK_API_KEY` (DsideOS/.env) has zero balance (402 confirmed live,
  2026-08-24) — the "5M free tokens" signup promo did not apply to this key.

**Unchanged, not part of this decision:**
- Grounding judge: `gpt-5.4-nano` (production `.env` override — code default
  is Haiku, server overrides it). Must stay a different model than the
  drafter; both gpt-oss-120b and any parked candidate above satisfy that.
- Embedding model: `text-embedding-3-small`, dimension-locked to the existing
  corpus — not swappable without a full re-embed (see §3).

## 9. Augmented Prompt

Status: not yet audited

## 10. Grounding / Verification

Status: not yet audited

## 11. Evaluation

Status: not yet audited

---

# Parked workstreams (not RAG stages — resume after the rebuild)

## A. Two-mode generation: RAG only where a knowledge gap exists

Decided 2026-09-09. RAG exists to close a KNOWLEDGE GAP, and that gap is real
only for Uttarakhand-specific material — tested earlier: the internet is an
unreliable source for UK exam facts. It is NOT real for national syllabus
content (Indian polity/geography/economics, reasoning, maths, computer
fundamentals): a frontier model already knows these better than our corpus, and
retrieving passages to tell it what Article 14 says is strictly worse than
asking it directly.

| | UK subjects | National subjects |
|---|---|---|
| subjects | uk-history, uk-geography, uk-culture, uk-general-studies | general-gk, computer |
| retrieval | yes — corpus is the only reliable source | none |
| grounding | yes — the whole point | not needed |
| topic source | syllabus + mined subtopics | model, guided by prompt |
| ~Q per 100 | ~46 | ~35 |

**`hindi` (19 Q) genuinely straddles both** and needs splitting at TOPIC level,
not subject level: grammar (संधि, समास, अलंकार, वर्तनी) has no knowledge gap,
but उत्तराखण्ड की बोलियाँ (कुमाउनी/गढ़वाली/जौनसारी) and regional literature are
exactly the niche-and-unreliable category.

**Knock-on benefits:** the worst-OCR'd corpus tier (`hindi`, `computer`) largely
leaves the critical path, so the garble gate and document-quality problem narrow
to the better-scanned UK books. Subtopic mining shrinks from ~19,000 passages
across 7 subjects to ~1,300 across 4.

**Implementation note:** `generate.py` has ONE path today. This needs a clean
seam, not `if subject in UK_SUBJECTS` scattered through the slot engine.

## B. Code-generated reasoning figures (तर्कशक्ति) — the moat

Decided 2026-09-09 to start with Approach A (fixed generators), move to hybrid
only if the variety ceiling proves real.

**Why this matters commercially:** भाग-2 (क) तर्कशक्ति is currently UNWIRED in
`syllabus.py` — no corpus, no generation path, we cannot generate reasoning
questions at all. This closes a hole, not an enhancement. And it is a genuine
moat: competitors can produce language questions with ChatGPT, but figures can
only be COPIED from existing banks — which means their answers already circulate
and students memorise them. Freshly generated figures with computed answers
cannot be memorised and have no bank to copy from.

**The core inversion — generate the answer FIRST, then render it.** Code picks a
transformation rule, applies it to a base shape, and therefore KNOWS the correct
output because it computed it. Question and answer key come from the same
deterministic function, so a wrong answer key is impossible by construction —
the same property that makes `build_match` bug-free. Diffusion models fail here
because they cannot guarantee "exactly 4 dots" or "rotated exactly 90°".

**Approach A — fixed parameterised generators (START HERE):**
1. A library of generator functions, one per UKSSSC figure type: mirror/water
   image · paper folding & punching · series completion · odd one out ·
   embedded/hidden figure · cube/dice net · counting (triangles/squares) ·
   analogy (A:B :: C:?)
2. Randomise parameters; apply the transformation programmatically — that result
   IS the correct answer
3. **Distractors by controlled perturbation** — not random shapes, but the
   correct answer with a PLAUSIBLE mistake applied (rotated wrong direction, one
   step too far, mirrored instead of rotated). Same "genuinely confusable" rule
   `PLAIN_PROMPT` already states for text.
4. Render SVG (exact, scalable, diffable) → rasterise to PNG for the existing
   docx/pptx builders.

**Reliability:** rendering is 100% deterministic, zero hallucination surface.
Real risks are elsewhere: *ambiguity* (two rules both fit → two defensible
answers; constrain each generator to one unambiguous rule), *visual clarity*
(overlapping strokes, too small to read in print), and *repetitiveness* (small
parameter space → recognisably similar questions — the variety problem again in
a new form).

**Approach B — LLM writes drawing code per question: REJECTED for now.**
Unbounded variety, but every eliminated failure mode returns, and the serious
one is unverifiable: the model's claimed answer may not match what its code
actually drew. That is the `build_assertion` unverified-`relation` bug in pixels
— and worse, because there is NO grounding gate for a figure (no passage to
quote against). A wrong figure ships silently and a student marks a correct
answer wrong. Making B safe requires a verification render (execute, then
programmatically check shape count, option distinctness, expected answer
delta) — real work, and exactly the mechanical-gate machinery we are reducing
elsewhere.

**Hybrid (the likely endpoint) — LLM proposes the RULE, code renders it.**
Model emits a structured spec, not code:
```json
{"type": "series", "base": "square_with_dot",
 "transform": [{"op": "rotate", "deg": 90}, {"op": "shade_next_cell"}],
 "steps": 4}
```
Model contributes creativity in rule design (where variety lives); code retains
execution and answer computation (where correctness lives). Same principle as
`formats.py` — model supplies semantics, code guarantees structure — except here
it is genuinely load-bearing, unlike in `build_assertion`.

**Why A first:** the rendering primitives and exam-paper layout work are shared
by all three approaches. Once primitives exist, exposing them as a spec
vocabulary is a small step, and real output will show whether the variety
ceiling is an actual problem or a theoretical worry. Realistic first version:
3-4 question types, a few days, mostly spent on making SVG layout look like a
real exam paper — the geometry itself is straightforward.

**Optional LLM role even in A:** writing the Hindi stem ("निम्नलिखित श्रृंखला में
अगली आकृति चुनिए") — boilerplate, could equally be a template.
