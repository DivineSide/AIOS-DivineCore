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

# PHASE 2 — NO-RAG PATH (2026-09-13)

Solves the blocker above: 54 of 100 questions (general-gk 32, hindi 19, computer 3) could not generate AT ALL, because those subjects have zero sectioned passages. Rather than tag corpus that does not exist well enough, the topic layer is authored directly.

## What shipped

- **`worker/taxonomy_data/uksssc-master/*.json`** — hand-authored topic trees for all 7 subjects, **1,354 leaves / 275 facets** total. Two levels: `facet` (a verbatim span of the commission's own syllabus bullet where the bullet is a comma list, so level 1 is checkable against the PDF) → `leaf` (a question-sized topic, authored). Written by reading each subject's official bullets alongside ~90 real PYQs pulled from our own `pyq_chunks` — no internet, no API calls.
- **`worker/taxonomy.py`** — the loader/sampler. `sections_for(subject, n, conn)` returns `[(leaf_label, []), ...]`, deliberately the same shape as `rag/sample.py`'s, so `generate.py` binds either source to one name. Empty list = the passage slot.
- **`batch_gen.NORAG_SYSTEM`** — parallel prompt for knowledge-only generation. `BATCH_SYSTEM`'s "read the section, pick a sentence" and "point to the sentence that makes the key correct" are unsatisfiable with no passages; the no-RAG variant asks for the model's own knowledge and explicitly bars current-events/officeholder facts. `build_batch_prompt` picks it automatically when every passage list is empty. `_schema`/`parse_batch` needed zero changes — already format-driven, not passage-driven.
- **`generate._sections_for`** — single source-selection point. Asks the DB whether the subject has any sectioned passage; falls to taxonomy if not. Used by BOTH the main pass and the top-up round so a paper's provenance cannot switch mid-run.
- **Migration 009 + reuse tracking** — `taxonomy_leaf_reuse`, mirroring migration 007's passage cooldown for leaves. Same `used_ago` age-in-generations mechanic, same `REUSE_COOLDOWN=5`.

## Verified live

- `computer` 3/3 delivered, **zero drops**, on gpt-oss-120b via Groq — real exam-grade questions from leaf labels alone, no retrieval.
- Six simulated rounds on `computer`: **zero overlap** between consecutive papers; cooldown ladder confirmed releasing leaves back to eligible after 5 generations.
- RAG path (`uk-geography`) confirmed unaffected — still `BATCH_SYSTEM`, still real passages.

## Decisions worth remembering

- **Leaves carry no difficulty tag.** An earlier pass tagged each leaf easy/moderate/hard so `blueprint`'s 50/30/20 could pick intrinsically-matching topics. Dropped on Mayank's call — a taxonomy is a topic chart, not a question plan. Difficulty is still assigned per QUESTION by `blueprint`, as before. (Symptom that prompted it: three separate authors, me included, all skewed hard — uk-culture came out 18/41/40 — because the interesting material in a subject genuinely is the niche material.)
- **Current affairs excluded, not special-cased.** `general-gk` bullets 23-24 carry only structural/evergreen leaves. A model with a knowledge cutoff generating "who currently heads X" ships confidently wrong answers; `NORAG_SYSTEM` bars it at the prompt level too.
- **Reuse keyed by `(subject, family, label)`** — a string key, because leaves live in JSON, not a table. Consequence: renaming a leaf resets its history (cold start, not corruption).
- **`GEN_BATCH_MAX_SECTIONS_NORAG=40`** separate from the RAG cap of 6. No-RAG batches are ~5x cheaper per section (~1,900 tok for 20 leaves vs ~8,984 for 4 RAG sections), so the RAG cap would have thrown away Phase 2's main advantage.

## Bugs found by RUNNING it, not reading it

Same pattern as Phase 1 — every one of these passed code review and failed a test.

- **Eligibility asked backwards.** `taxonomy_leaf_reuse` only gets a row once a leaf is USED, so "which leaves are eligible" (`used_ago IS NULL`) returned the *just-used* ones as the only candidates — paper 2 reused all 8 of paper 1's leaves. The file is the source of truth for what EXISTS; the table only records what is COOLING. Ask for the cooling set and subtract. (Copied the query shape from `rag/sample.py`, where asking for eligible IS correct, because every passage already exists as a row.)
- **One paper burned N generations of cooldown.** `advance_generation` ran per-subject while subjects run concurrently, so each subject aged every *other* subject's fresh marks. A 7-subject paper consumed ~7 generations of a 5-generation window, leaving leaves at `used_ago` 1..4 instead of a uniform 1 — the cooldown was worth roughly one paper, not five. Fixed by splitting: `mark_used` stays per-subject, `advance_generation` moved to a paper-level `_advance_generation()`. **This affected the PASSAGE path identically** and had been silently degrading RAG-path variety since migration 007 shipped.
- **Stale rows starved the LRU fallback.** A renamed or deleted leaf leaves its row behind (migration 009 tolerates this deliberately — no cleanup job). Those stale labels consumed the fallback query's `LIMIT` and were then filtered out in Python, so the caller came up short: measured on a 74-leaf subject with 50 stale rows, a 12-question request **delivered 4**. Filter to known labels inside SQL (`label = ANY(%s)`), never after the LIMIT.
- **A "fast path" that defeated its own purpose.** `_KNOWN_NORAG_SUBJECTS` skipped the has-sections DB check for five subjects — including `uk-history` and `uk-culture`, the two queued for tagging. Running `tag_sections.py` on them would have had no effect. Removed; routing is one indexed `LIMIT 1`, so a subject that gains sectioning switches automatically.

## Archived alongside Phase 2

Moved to `.archive/dsideos-dead-code/` (on-disk, gitignored — same convention as the slot engine). Both had zero callers; neither is deleted, because the reasoning in them may be wanted back.

- **`blueprint.exam_format_plan` + `_jitter` + `subject_format_mix`** — the per-subject format pre-pass `generate_exam()` used to run. The batched engine plans format inside `generate_questions_batched`, so the whole chain went dark. The idea is still sound (history really does carry more match questions than computer; a flattened ratio rounds rare formats to 0 at 5-16 questions per subject) and the measured-from-corpus version with additive smoothing is preserved intact. If revived, check `pyq_chunks.format` NULL coverage first.
- **`syllabus.topics_for`** — exam mode's old topic seeder. It fed official syllabus BULLETS to the generator as topics, but a bullet is a section heading, not a question-sized topic (`formats.py` even had a gate rejecting stems that echoed one). Phase 2's taxonomy does that job at the right granularity. **`worker/syllabus.py` itself stays**: its `TOPICS` dict is the canonical page-by-page transcription of the UKSSSC 2026 syllabus and is what the taxonomies were authored FROM — reference data, and the thing to check a taxonomy against.

## Known limits

- **Nothing checks a generated fact is true** — unchanged from Phase 1, and more exposed here: the RAG path at least constrained the model to supplied text, this path is the model's own knowledge. Same tradeoff, consciously taken.
- **`taxonomy.REUSE_COOLDOWN` is hardcoded at 5** while `rag/sample.py`'s is env-configurable (`RAG_REUSE_COOLDOWN`). Deliberate for now (the two pools are different sizes and may want different tuning), but they should be aligned once Phoenix shows real exhaustion rates.
- **PYQ format examples are still format-blind.** `_style_examples` pulls k=2 at subject level, so a `match` batch is shown `plain` examples (466 of 520 general-gk PYQs are plain). Matters more here: with passages gone, PYQs are the only signal about what a real paper looks like. Corpus can support it — every subject has enough `plain`, and `match` has 12-37 per subject.
- **Scarce formats stay scarce.** `assertion` (7 corpus-wide), `order` (9), `statement` (33) are genuinely rare in real UKSSSC papers — a web-sourcing pass confirmed the scarcity rather than fixing it, and found zero verbatim computer-subject `match` questions.
- **`uk-history` and `uk-culture` now have BOTH** a taxonomy and (eventually) sectionable corpus. `_sections_for` prefers real sections when they exist, so tagging those books later silently switches them back to the RAG path — intended, but worth knowing.

---

# PHASE 3 — REASONING (तर्कशक्ति), CODE-ONLY (2026-09-15)

The first question source in this pipeline where **the answer is computed, not asserted**. Phases 1 and 2 both end with a model stating a fact that nothing verifies. A direction-and-distance question depends only on the walk we invented, so code picks the parameters, computes the answer from those same parameters, and fills a template. **No model call, no retrieval, no DB.**

## What shipped

- **`worker/reasoning/`** — `pools.py` (cosmetic vocabulary) + 5 generators (`direction`, `series`, `coding`, `relations`, `arrangement`) + a registry. Each generator is `generate(rng) -> question dict`, pure, returning the same shape `formats.build` produces.
- **Branch in `generate_questions_batched`** *before* the DB connection opens — everything below it (sections, style examples, prompt building, drafting, top-up) is machinery for extracting facts from a model.
- **`reasoning: 0.10` in all 4 `SUBJECT_MIX` families**, carved back out of `general-gk` which had been absorbing it (the file's own comment said so). A 100Q vdo-vpdo paper now allocates exactly 10 — matching the real papers.
- **`tests/test_reasoning.py`** — 27 tests, 1000 seeds per generator (150 for the brute-force uniqueness proof), ~23s.

## Grounded in a full PYQ survey, not one paper

`corpus/reasoning-reference/SURVEY.md` records every available paper. The findings changed the plan:

- The **official syllabus specifies no per-section counts at all** — only "100 questions, 100 marks, 2 hours". Reasoning's share is a product decision; Mayank set 10.
- The block is **exactly 10 questions** in both papers that have one — at Q21-30 in one, Q91-100 in another. Count stable, position arbitrary.
- **One surveyed paper has no reasoning at all** (lekhpal-patwari 2025).
- **13 of 18 catalogued questions need no figure.** Text-only first was the evidence-driven call, not a shortcut.
- Real distractors are **the partial results of the solution path** (3 and 4 flank the true 5 in a 3-4-5 walk), never random near-misses. Every generator reproduces this.

## Gate exemption

Reasoning bypasses `validate_question` and `PaperGuard` entirely — the branch never calls them, so no signature or caller changed. Each gate is a proxy for an LLM failure mode that cannot occur here, and two were **measured** blocking real content:

- **numeric budget**: caps numeric answers at 20% *per subject* = 2 per 10-question block. Simulated against a real UKSSSC block: **3 of 10 rejected.** A distance answer is numeric by nature.
- **`_YEAR` 600-2026**: a series containing `2048`, or a coding answer of `3456`, is read as an implausible CE date. **Both rejected** in testing.

`pipeline/validate.py` (build-time) still runs and passes 200/200 — it checks document shape, not model behaviour.

## Bugs found by RUNNING it

- **Gendered participle in a shared pool** — `मुड़ा और` sat in `TURN_WORDS`, producing "उषा ने … मुड़ा और … चली". Now gender-neutral only; anything that inflects belongs in a `*_M`/`*_F` pair. Regression-tested.
- **Visible term offered as a distractor** — series "10, 22, 34, 46, ?" offered `46`. A candidate eliminates it without arithmetic. Shown terms are now banned from the option set.
- **Type clustering** — round-robin-then-shuffle defeated its own purpose: **51 of 200 blocks had a run of 3+ identical types**, including three consecutive coding questions. Now shuffled *within* each round: 0 of 300.
- **A uniqueness check that only searched half the space.** `arrangement._is_unique` permuted ORDERINGS while holding the true gaps fixed, so it could not detect an unpinned interior point: "D→C=23, D→B=14" plus two betweens left A free to slide, and A→C could be anything from 10 to 22. The generator shipped an unanswerable question and the check passed it. Fixed by searching gap assignments too; the clue set now states every consecutive gap.
- **Series variety was 20x thinner than claimed** — measured 1,426 distinct stems in 20,000 seeds (7%) against direction's 99.8%, because a series has **no cosmetic slots** (no names, verbs or units). Widening the parameter ranges took it to 6,586 (33%). The lesson generalises: a type's variety ceiling is set by whichever axis it lacks.

## Measured variety (20,000 seeds)

| type | distinct stems | why |
|---|---|---|
| direction | 19,965 (99.8%) | 60 names x 2 verb sets x 3 units x walk parameters |
| coding | 12,460 (62.3%) | 28 words x 4 rules x k x 2 output modes |
| series | 6,586 (32.9%) | parameters only — no cosmetic axis exists |

## Phase 3c — figures (2026-09-16, shipped)

**All five figure types are built**: `dice`, `triangles`, `clock` (drawn dial), `figseries`, `venn`. 16 types total (11 text + 5 figure). 115 tests. Verified end to end: 14/14 questions kept by `run_pipeline.validate` (zero dropped), 7 figure PNGs embedded in both `build_paper` and `build_paper_format2`.

**Pillow only** — matplotlib, cairo, svglib and reportlab are absent from both the environment and `worker/requirements.txt`, which is all the Docker image installs. Pillow was already a dependency, so figures added none. 3x supersampling + LANCZOS because `ImageDraw` has no antialiasing of its own.

**Generators stay pure; one module touches disk.** A figure generator returns a JSON `_figure` spec and never a file; `reasoning/render.py` is the only writer. That keeps figure logic testable at thousands of seeds/second and lets the same spec render as SVG or a web preview later without touching a generator.

**Rendering RAISES rather than skipping — the hazard that justified the split.** `run_pipeline.validate` checks image existence and silently DROPS questions whose files are missing, then ships the rest: a figure that fails to write produces a *short paper with no error anywhere*. `render.py` verifies every write and raises `FigureError` instead, turning a silent shortfall into a loud failure at generation time.

**Three pre-existing bugs found and fixed while wiring this up:**
- `build_paper.py:286` discarded `add_figure`'s return value while every other branch appended to `q_paras`, so the stem figure was excluded from `keep_question_together` — a column break could land between a question's figure and its options.
- **`build_paper_format2.py` had ZERO image support** (grep: 0 hits). Every figure silently vanished on that layout, and a question whose options are images was dropped outright by the stem/options guard. It now renders both `image` and `option_images`, sized smaller (4.0x3.4cm stem, 3.0x2.6cm option) because the figure sits in a table cell, not a page column.
- Both builders now share the same path-confinement rule, so a relative `figs/q7.png` resolves identically and a malicious ref is rejected in both.

**Correct by construction, per type:**
- `clock` — the dial was BUILT but never attached: `clock.py` emitted no `_figure`, so `figures._draw_clock` was dead code and the questions printed as text. Found by reading the first real PDF, not by a test. Now ~50% of clock questions show a drawn dial instead of printing the time, and a test asserts the drawn variant never prints the time in its stem (which would make the dial pointless).
- `dice` — three isometric views; the bottom face is forced by which faces never appear beside the top. Reproduces the real vdo-vpdo Q21 exactly on seed 1. (The printed key "4,4,6" contradicts its own derivation — the same OCR damage as Q91's clock key; built from the derivation.)
- `triangles` — the count is EXHAUSTIVE over every triple of segments, never a formula. Verified against 1/5/13/27 and the real Q26's keyed 27. An earlier construction paired mismatched fractions and counted 21 where a 3-row triangle has 13.
- `figseries` — the true series is *generated* by rotating symbols one quadrant per step, then two figures are swapped; the key is the index we swapped, never inferred from the picture. Only UNIQUELY-restoring swaps are emitted, because a period-4 rotation over 4 shown figures otherwise admits a second valid swap and two defensible answers. The rule was decoded from the real Q22 strip (read off the unwatermarked Hindi column at 3x) and reproduces its keyed answer (A).
- `venn` — the set RELATION is chosen first; the correct layout and the Hindi description both derive from it, so picture and words cannot disagree. The only type using `option_images`. A test re-derives each relation from raw circle coordinates and asserts no two layouts draw the same arrangement.

**Tests re-derive answers from the PICTURE, not the generator.** The `figseries` test solves each question the way a candidate would — both rotation directions, all six swaps — and fails if more than one figure number is justifiable. 3,000 seeds, zero mismatches.

**Font portability is a real trap, not a theoretical one.** Local Windows has Arial; the container has Devanagari fonts but **no guaranteed Latin TTF**, and dice digits are Latin. Fonts resolve through a documented chain ending at `ImageFont.load_default()`, with a test that clears the candidate list and asserts resolution still succeeds. `figseries` symbols are drawn as geometry rather than glyphs for the same reason — a missing glyph renders as a blank box, which in that type would destroy the very thing being compared.

### Found by printing it (2026-09-17)

Three defects that every test passed over, surfaced only by building a real PDF and reading it:

1. **The clock dial was never wired in** (above) — the renderer existed and was correct; the generator just never emitted a spec.
2. **The figure-series strip printed illegibly.** `build_paper` caps a stem figure at 4.8cm WIDE and 4.0cm tall, and a 5-square row is ~3:1 — so it printed 4.8 x 1.6cm, under 1cm per square for four symbols. The strip now WRAPS to 3 per row (1.43cm per square after the height cap). The test asserted aspect ratio, which was the wrong property; it now asserts the printed size of one square.
3. **A 100-question block silently delivered 95.** Dedup keyed on stem+options, but `figseries` uses ONE fixed stem by design — the picture is what varies — so every figseries question after the first looked like a duplicate. The shortfall was a log line, nothing failed. Dedup now folds in the figure spec; 100/100 delivered, and the measured ceiling in the table above is superseded.

**The lesson is the same one the survey taught:** correctness tests and print tests are different tests. Every one of these passed the correctness gate, because none of them produced a WRONG answer — they produced a right answer nobody could read, or no question at all.

## Productisation (2026-09-17)

`/api/generate` reached reasoning only through **exam mode** (the blueprint allocates 10% to reasoning in all four families), because `"reasoning"` was missing from the API's `VALID_SUBJECTS`. A caller asking for a reasoning-only worksheet got HTTP 400. Added, plus the dev dashboard's hardcoded copy of the same list. Subject mode now serves counts up to 100.

Note the API deliberately does NOT import worker modules (separate container), so `VALID_SUBJECTS`/`VALID_EXAMS` are hand-synced copies — a new subject must be added in both places.

## Deferred

**Figure matrix completion** (real vdo-vpdo Q28) — a 3x3 grid whose missing cell is chosen from four option images. Needs a two-dimensional pattern rule rather than the single rotation `figseries` uses, and it did not appear in the second surveyed paper: the lowest-value figure type per unit of work.

**All twelve text types shipped** (2026-09-16): direction, series, coding, relations, arrangement, lettersum, calendar_year, grouping, household, clock, coded_relations, sufficiency. A 10-question block draws 10 different types. 52 tests.

Phase 3b notes:
- **`util.py` extracted first** — the distractor routine was already copied three times; twelve types would have made it twelve.
- **Two source questions were re-solved before being modelled.** The calendar key (2009 → 2015) and the logical-grouping key (→ गोविन्द) are both correct. The clock water-image key is **unsolvable** — none of its List-II times is a correct image of any List-I time, and its four pairings imply four different transformations. That type was built from the definition (`720 − t`) instead, and emits `plain` rather than the source's `match` layout.
- **A wrong composition shipped and was caught by reading output, not by a passing test count**: `coded_relations` had `("wife","son") → "mother"`, but if R is P's wife and P is S's son, R is S's daughter-in-law. Every entry in that table is now hand-verified.
- **Dedup had to widen twice.** First to reject on *either* the semantic key or the stem (a fresh word set was reusing a printed stem); then to include the OPTIONS, because `lettersum` carries its whole question there — 4,975 real questions behind 6 stem templates, which starved a block.
- **A 100-question hand-read (2026-09-16) found 3 more issues**, all in the types that encode domain logic rather than compute a value: a second wrong `_COMPOSE` entry (`("son","mother")` claimed grandson; X and Z are siblings), `grouping` offering names absent from its own statements (436/3000), and 62% of `sufficiency` questions stating the age outright. The first was a WRONG ANSWER KEY; the other two made questions trivially eliminable. All three now have regression tests, and the composition table is verified against a concrete family model rather than itself. **The other nine types produced nothing wrong across 99 questions** — the architecture held; the hand-written tables were the soft spot.
- **Difficulty tagging added (2026-09-16)**: every reasoning question now carries `difficulty`, derived from its own parameters. Measured 38/41/21 against the 50/30/20 target — hard on target, easy ~12pts light. Left as-is deliberately: intrinsic difficulty cannot be dialled to a target the way the LLM path's allocation can, and forcing it would mean restricting generators to trivial parameter ranges. A test guards a sane band plus the rule that no type may be stuck on one level (`lettersum` was, and silently dragged the mix).
- **Ceiling measured honestly**: blocks up to 100 now fill exactly (100/100 after the figure-dedup fix, 2026-09-17); 200 delivers ~191 and 300 ~277, limited by the thinnest types (calendar_year 153 distinct, clock 852). A 10-question exam-mode block and a 100-question subject-mode worksheet both fill.

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
