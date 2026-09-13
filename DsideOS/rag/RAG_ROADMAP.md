# RAG Build Roadmap

Tracks the production-RAG checklist for DsideOS, one stage at a time.
Each section fills in as that stage is audited/built/tuned — status,
what's live, what's missing, decisions made. Blank sections below are
not-yet-covered, not skipped.

See also: [rag_learnings.md](../rag_learnings.md) (general RAG theory
reference) and `DsideOS/CLAUDE.md` (accumulated production incidents).

---

# PHASE 1 — COMPLETE (2026-09-13)

The RAG generation path, rebuilt. Detail lives in the stage sections below;
this is the index. Phases 2 (no-RAG national subjects) and 3 (code-generated
reasoning figures) are in "Parked workstreams" at the end.

## What shipped

| area | state |
|---|---|
| **Syllabus** | Canonical transcription of the signed 2026 UKSSSC PDF. 156 hand-invented topics → 76 traceable ones. तर्कशक्ति added (26 topics, previously absent entirely); Hindi literature dropped (the 2026 revision removed it); computer gained AI/ML/IoT/blockchain/cloud/GenAI. |
| **Retrieval** | Metadata filter + `ORDER BY RANDOM()`. No embeddings, no HyDE, no PYQ semantic search at query time. One indexed query. |
| **Variety** | 5-generation cooldown (`used_ago`, migration 007). Two consecutive papers share ZERO passages and ZERO sections — the finding that opened this audit, solved deterministically rather than probabilistically. |
| **Sections** | Topic layer taken from the BOOKS' own authored headings (`section`, migration 008), recovered from `.reocr` transcripts by exact-offset anchoring. uk-geography 371/385 → 58 sections; uk-general-studies 191/267 → 26. |
| **Batching** | One call per (subject, format), each with its own strict JSON schema. ~1 API call per question, down from ~4. |
| **Formats** | All five generate. Non-plain formats still return FACTS ONLY — code computes the कूट grid and answer letter, so a structurally inconsistent match/order question stays impossible. |
| **Difficulty** | 50/30/20, allocated INDEPENDENTLY of format (tying them caps hard at ~13%, since the real mix is ~87% plain). Taught by per-subject definition + three worked exemplars; only the current subject's block is injected. |
| **Top-up** | Regenerates drops on fresh sections at the SAME (format, difficulty), so gate rejections no longer skew the paper easy. |
| **Subject mode** | Rebuilt on the batched engine. Two optional dropdowns (one format, one difficulty for the whole sheet); unset falls back to the realistic mix. |
| **PYQ corpus** | All 4 generatable exams covered, 100% format-tagged. Backfilled 544 NULL rows at zero API cost; ingested police-constable (the only gap) with no OCR and no paid classification. |
| **Prompt** | Rewritten as a five-step construction method. Prohibitions 22 → 9. |
| **Provider** | Default `gpt-oss-120b` on Groq. `GEN_PROVIDER=openai` switch works with identical constrained decoding. |
| **Slot engine** | Archived to `.archive/dsideos-slot-engine/`. `generate.py` 1,568 → ~800 lines. |

## Bugs found by RUNNING it, not reading it

Every one of these surfaced only under real execution:

1. `_GroqTokenBucket.acquire()` **hung forever** when a request exceeded the whole per-minute budget — an invisible deadlock, no error, no log.
2. Chunk budget under-counted **twice**: first by using a fixed section count (sections range 1–31 passages), then by sizing against `BATCH_SYSTEM` alone while the real prompt also carries the difficulty block, format contract and PYQ examples (~1,100 tokens short).
3. Attribution phrases ("जैसा कि सामग्री में कहा गया है") killed **6/6** questions in the first batched run — the exact failure that killed Sarvam-30b.
4. `_shape_class` read "17.98 मीटर" as text, so unit-bearing numbers **bypassed the numeric-answer budget entirely**.
5. `_statement_options` rejected **every** 2-statement draft by construction, while the prompt explicitly invited "2 to 3 statements" — silent, burned all 3 attempts.
6. Table references in stems ("तालिका के अनुसार") passed every gate.
7. Mixed-script OCR damage (`उत्तarakhand`) leaked into stems.
8. Subject mode called `generate_questions()` **after it was archived** — an AttributeError on any subject-mode request.
9. `_seed()` went to the archive while still being called — a NameError `py_compile` cannot see.

## Deliberate decisions worth remembering

- **Grounding removed** from the generation path. Nothing now verifies a fact is TRUE; shape, form and paper-level distinctness are all still checked. `ground.py` is untouched — re-enabling is one line.
- **Gate pruning investigated and rejected.** Every surviving `validate_question` check tests something a JSON schema cannot express (distinctness, Devanagari ratio, OCR garble, shape-eliminability). Only pure type/count checks became unreachable.
- **Subtopics rejected** in favour of book sections + reuse tracking — invented names are not canonical and become maintenance debt.
- **A "cross-question awareness" prompt section was added and then removed** — it was never part of the design, and PaperGuard owns paper-level dedup anyway.

## Known limits going into Phase 2

- **Section tagging** for uk-history, uk-culture, hindi — needs Mayank's per-book taxonomy. uk-culture needs a different approach: 588 of 647 passages have no transcript.
- **Syllabus↔section mapping layer** — designed (sections describe the corpus, syllabus describes the exam, a small table joins them) but not built.
- **No truth check** — see grounding above.
- **Numeric drift** where a section is a statistical table (migration, census): "pick a stated fact" and "prefer a name over a number" genuinely conflict there. A source-material limit, not a prompt one.
- **~23 min per 100Q paper** on Groq's free tier — the 8,000 tok/min ceiling is a per-REQUEST cap, not just a rate limit, so it forces ~4-section chunks. Lifting it is one env var.

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

**Built and verified (2026-09-11):**
1. `section` column + `rag/tag_sections.py` — the BOOK'S OWN authored headings,
   read from the `.reocr` transcript (which retains ~2x the structure that
   survived chunking, since ingest split on sentences and build_passages merged
   on char count — headings were never a boundary). uk-geography: 371/385
   tagged, 58 sections after merging undersized ones (1-passage sections went
   54 → 2). Syllabus topics map ONTO sections separately, so a syllabus
   revision rewrites ~8 mapping rows, not thousands of tags.
2. `rag/sample.py` — `sections_for()` / `mark_used()` / `advance_generation()`.
3. Wired into `generate.py` as `generate_questions_batched` (GEN_BATCHED=1).

**Measured result:** two consecutive papers shared ZERO passages and ZERO
sections. The variety problem that opened this audit is solved deterministically.

**Bugs this surfaced, all fixed:**
- `_GroqTokenBucket.acquire()` HUNG FOREVER when one request exceeded the whole
  per-minute budget (a 10-section batch needs ~20k vs a 7.2k/min ceiling). It
  now raises instead of looping — an invisible deadlock became an actionable
  error.
- Batch chunking must be TOKEN-aware, not section-count-aware: sections range
  from 1 to 31 passages, so "4 sections" was 3k tokens for one subject and 8k
  for another, and the oversized ones failed outright.
- `_shape_class` read "17.98 मीटर" as text, so unit-bearing numbers bypassed
  PaperGuard's numeric-answer budget entirely.

**Still open:**
- Tag the other three UK subjects (blocked on Mayank's per-book taxonomy read).
  uk-culture needs a different approach — 588 of its 647 passages come from
  books with no `.reocr` transcript, so nothing can be anchored.
- The syllabus↔section mapping layer (see the Phase 1 summary at the top).

(An earlier note here flagged grounding rejections as the dominant drop reason.
Grounding was removed from the generation path on 2026-09-12 — see §10.)

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

Status: rewritten 2026-09-12 as a CONSTRUCTION METHOD

BATCH_SYSTEM was 22 prohibitions across 74 lines with no section describing how
to actually build a question — a fence, not a method. Now five ordered steps:
find the fact -> make the question standalone -> build distractors from one
category -> prefer a name over a number -> write the reason as the bare fact.
The bans survive as consequences inside the step they belong to.

Per-call the prompt also carries: the subject's difficulty block (only that
subject's, ~1k chars — all seven would dilute the steer), the format contract
when the batch is not plain, and 2 real PYQs from this exam+subject as register
reference, sampled fresh each run.

Honest result: prohibitions 22 -> 9, but question quality did not measurably
improve and numeric answers stayed high. Root cause is the SOURCE, not the
prompt — sections built from statistical tables (migration, census) contain no
non-numeric checkable facts, so "pick a stated fact" and "prefer a name"
genuinely conflict there. A prompt cannot fix that; section quality can.

REMOVED 2026-09-12: an "ACROSS THE WHOLE BATCH" section telling the model to
avoid duplicating entities across its own questions. It was never part of the
design — added on the assumption that cross-question awareness was a benefit of
batching. It is also near-redundant: sections are distinct by construction, and
PaperGuard owns cross-question dedup at PAPER level, which a batch of ~4 cannot
see anyway.

## 10. Grounding / Verification

Status: REMOVED from the generation path 2026-09-12 (deliberate)

ground.py still exists and is untouched; nothing calls it. The batched prompt
constrains each question to ONE section's material, which is tighter than the
old per-slot prompt, and a measured 10/10 run had zero grounding rejections —
the gate was costing a call per question to reject almost nothing.

STATED TRADEOFF: nothing now verifies a generated fact is TRUE. Constrained
decoding guarantees shape, validate_question guarantees form, PaperGuard
guarantees paper-level distinctness — none read for truth. A live test produced
schema-perfect JSON asserting N.D. Tiwari was Uttarakhand's first CM (it was
Nityanand Swami); that class of error now ships. Re-enabling is one line.

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
