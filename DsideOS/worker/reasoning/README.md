# worker/reasoning — तर्कशक्ति questions, generated entirely by code

**No model call. No retrieval. No database.** This is the only question source in
the pipeline where the answer is *computed* rather than asserted, which is the
whole reason it exists — see `__init__.py`'s docstring for the full argument.

Grounded in a survey of every available PYQ paper:
`corpus/reasoning-reference/SURVEY.md`.

| file | responsibility |
|---|---|
| `__init__.py` | **LIVE.** The registry (`TYPES`) and `generate(count, seed)`. Spreads a block evenly across types, guarantees distinct stems, logs a shortfall. The only module `generate.py` imports. |
| `pools.py` | **LIVE.** Shared *cosmetic* vocabulary — names (gendered, Uttarakhand-appropriate), places, units, verb forms, stem phrasings. Nothing here can change an answer. |
| `direction.py` | **LIVE.** Direction & Distance. Builds a 4-leg walk from a Pythagorean triple so the answer is always a whole number. Distractors are the axis displacements and the Manhattan sum — the partial results a candidate gets by stopping early. |
| `series.py` | **LIVE.** Number Series. Four rules; terms held as `Fraction` so a ×1.5 series stays exact (13.5, 20.25 — as the real papers print). Distractors are wrong-base and neighbouring-constant applications. |
| `coding.py` | **LIVE.** Coding-Decoding. Four position-based ciphers, two output shapes (per-letter sequence, positional sum). Distractors include a transposition, which is the one genuinely hard option. |
| `relations.py` | **LIVE.** Blood Relations. A fixed 3-generation family tree; a random path through it is rendered as nested possessives and the relation is read off the tree. Rejection-samples common endpoints so the answer key is not 43% "पिता". Elders take the honorific plural. |
| `arrangement.py` | **LIVE.** Linear Arrangement. Positions fixed first, clues read off the true layout, then `_is_unique` brute-forces every ordering AND every gap assignment to prove the asked distance is pinned before the question ships. |

| `figures.py` | **LIVE.** Turns a figure SPEC into a PIL image — Pillow only (nothing else is in the production image). Supersamples 3x and downsamples with LANCZOS, since ImageDraw has no antialiasing. Crops to the ink so the builder's aspect-fit gives each figure the whole box. Resolves fonts through a fallback chain ending at Pillow's bitmap default. |
| `render.py` | **LIVE.** The ONLY module here that touches disk. Writes `figs/qN.png` under the job's input dir, rewrites the spec as `q["image"]`, and **raises** on any failure — because `run_pipeline.validate` silently DROPS a question whose image is missing and ships the paper short. |
| `dice.py` | **LIVE (figure).** Three isometric cube views; the bottom face is forced by which faces are never seen beside the top. Rejects any view set that does not pin a unique answer. Reproduces the real vdo-vpdo Q21 exactly on seed 1. |
| `triangles.py` | **LIVE (figure).** "How many triangles?" over a subdivided triangle or a diagonal strip. The count is EXHAUSTIVE — every triple of segments tested for a real triangle — never a formula, because a wrong formula is a wrong answer key that nothing downstream catches. Verified against 1/5/13/27 and the real Q26's keyed 27. |
| `clock.py` | **LIVE (text + figure).** Water/mirror image of a clock time. ~50% of questions SHOW a drawn dial instead of printing the time (both forms appear in real papers); the drawn variant must never print the time in its stem. The transformation is `720 - t` / `360 - t`, self-inverse across all 720 times; the dial is rendered from the same time, so picture and key cannot disagree. |
| `venn.py` | **LIVE (figure, option images).** "Which diagram fits this description?" A set RELATION is picked first; the correct layout and the Hindi description are both derived from it, and the three distractors are layouts of different relations. The ONLY type using `option_images` — four PNGs per question. |
| `figseries.py` | **LIVE (figure).** "Swap two figures to fix the sequence" (real vdo-vpdo Q22). Five squares split by both diagonals, four symbols rotating one quadrant per step. The true series is generated, then two figures are swapped — the key is the index we swapped, never inferred. Emits only swaps that are UNIQUELY restoring, so no question has two defensible answers. |

Tests: `tests/test_reasoning.py` — **these are the gate.** No runtime validator
runs on this path (see the exemption note in `__init__.py`), so a wrong solver
would otherwise ship silently. Each test re-derives the answer by a *different*
path than the generator used; the direction test parses the rendered Hindi stem
rather than reading the generator's internals, because the student sees the stem.

## Adding a generator

1. New module exposing `generate(rng: random.Random) -> dict` with keys
   `stem`, `options` (4 distinct strings), `answer` (`"a"`-`"d"`), `format`
   (`"plain"`), `reason`, `_type`.
2. Register it in `TYPES`. Allocation and stem-distinctness come free.
3. Add tests that re-solve independently. **Do not** reuse the generator's own
   helper to check its output — a shared bug cancels out and the test passes on
   wrong output.

Two rules learned the hard way:

- **Cosmetic slots must be gender-neutral or paired.** A gendered participle in
  a shared pool produced "उषा ने … मुड़ा और … चली".
- **Never offer a value the student can already see** as a distractor. A series
  printing `46` offered `46` as an option; an arrangement stem stated
  "C से A तक की दूरी 5 किमी" and then asked for C→A.
- **Prove uniqueness over the whole search space, not a slice.** `arrangement`'s
  first uniqueness check permuted orderings while holding the true gaps fixed,
  so it could not see an unpinned interior point. Caught by the test suite, not
  by review.
- **Dedup on meaning, not on the rendered string.** Two relation questions with
  the same chain and different speaker names are the same question; publish a
  `_dedup_key` when the stem carries cosmetic variation.
- **...but dedup on the STRING too.** The inverse also bites: two `lettersum`
  questions with different word sets can draw the same phrasing and the same
  अधिकतम/न्यूनतम form, so the stems render identically while the keys differ.
  The registry now rejects if EITHER half collides. A tuple key is not enough —
  it only collides when both match.
- **A fixed stem is a duplicate waiting to happen.** `lettersum` and
  `calendar_year` shipped with one hardcoded stem each and immediately produced
  two identical-looking questions in one block. Every type needs 2-3 phrasings
  even when its parameters vary.
- **Verify a composition table by hand, entry by entry.** `coded_relations`
  shipped `("wife","son") -> "mother"` — wrong: if R is P's wife and P is S's
  son, R is S's daughter-in-law. It produced a confidently wrong answer key and
  only surfaced when the smoke-test output was read rather than counted.
- **A wrong lookup-table entry is invisible to structural tests.** `_COMPOSE`
  produced TWO wrong answer keys before a hand-read caught them, because the
  generator and the table agreed with each other. The fix is
  `test_coded_relations_composition_semantics`, which derives every entry from
  a concrete family model instead of trusting the table — verified to catch
  both historical bugs when they are reintroduced.
- **An option the student cannot see in the stem is not a distractor.**
  `grouping` offered names that appeared in none of its four statements
  (436/3000), because a person can land outside every property set. Every
  person must now be mentioned at least once.
- **Do not hand the answer away in a clue.** 62% of `sufficiency` questions
  contained a statement stating the age outright, which turns a
  reasoning-about-sufficiency question into a reading exercise. One such clue
  is legitimate ONLY for the "statement I/II alone is sufficient" case.
- **Particles are load-bearing in Hindi.** Distractors assembled from bare
  relation words with a hardcoded का produced "N, R का माता है". Build wrong
  options as complete phrases so each carries its own particle.

## Difficulty

Every question carries `difficulty` (easy/moderate/hard), derived from the
parameters that already exist rather than asserted — a 3-4-5 walk really is
easier than 7-24-25, a 2-step relation chain easier than a 3-step. It is
correct-by-construction like everything else here.

**Measured over 400 questions: 38% easy / 41% moderate / 21% hard**, against
`blueprint.DIFFICULTY_MIX`'s 50/30/20 target. Hard is on target; easy runs ~12
points light.

That gap is structural and left deliberately. Reasoning difficulty is
INTRINSIC — it falls out of each question's own parameters — so unlike the LLM
path, where `blueprint.allocate` hands out difficulty labels to hit a target, it
cannot be dialled. Forcing 50% easy would mean restricting generators to their
trivial parameter ranges, which buys the number at the cost of the questions.
The test guards a sane band, not the exact figure.

One rule learned here: **a type stuck on a single level is worse than no tag.**
`lettersum` keyed off one word's length while every word in its pool is 5-7
letters, so every question came out easy and silently dragged the paper's mix.
`test_difficulty_actually_varies` now fails any type whose threshold does not
discriminate over its own parameter range.

## Known ceiling

Each type has a finite parameter space, so a single block cannot exceed the
thinnest type's supply. **Measured after the 12-type build:**

| block size | short in 60 runs |
|---|---|
| 10 | 0 |
| 30 | 0 |
| 100 | all (delivers 100) |
| 300 | all (delivers ~277) |

At the 10-per-paper size this is nowhere near binding. The warning in
`generate()` names the generator that ran dry, so if it ever does bind the cause
is in the log rather than guessed at.

Distinct questions per type, 20,000 seeds. **Two numbers matter and they are
not the same one:** `stems` is what a reader sees, `keys` is how many genuinely
different questions exist. `lettersum` puts its whole question in the OPTIONS,
so it has 4,975 real questions behind only 6 stem templates — which is why the
registry dedups on stem *plus options*, not the stem alone.

| type | distinct stems | limited by |
|---|---|---|
| arrangement | 20,000 (100%) | layouts × gaps × labels |
| grouping | 20,000 (100%) | people × property sets |
| direction | 19,965 (99.8%) | names × verbs × units × walk |
| sufficiency | 18,439 (92.2%) | names × clue pairs × ages |
| coding | 12,460 (62.3%) | 28 words × 4 rules × k × 2 modes |
| series | 6,586 (32.9%) | parameters only — no cosmetic axis |
| relations | 6,287 (31.4%) | 22 chains × names |
| coded_relations | 2,937 (14.7%) | operator pairs × letters |
| clock | 852 (4.3%) | 12 h × 12 m × 2 transformations |
| household | 729 (3.6%) | family shapes × question forms |
| calendar_year | 153 (0.8%) | 51 years × 3 phrasings |
| lettersum | 6 stems / **4,975 questions** | word sets live in the options |

## Not here

**Every figure type from the survey is now built** — dice, triangle/square
counting, clock dials, figure series and Venn option diagrams. What remains
unbuilt is the *figure matrix completion* type (real vdo-vpdo Q28): a 3x3 grid
where the missing cell is chosen from four option images. It needs a
two-dimensional pattern rule rather than the single rotation `figseries` uses,
and it did not appear in the second surveyed paper, so it is the lowest-value
figure type per unit of work.

## Figure questions — what to know before touching them

**A missing PNG silently DROPS the question.** `run_pipeline.validate` checks
that every referenced image exists and drops the ones that fail, then ships the
rest — a short paper with no error anywhere. `render.py` therefore verifies
every write and raises instead. Do not "helpfully" make it skip.

**Generators never touch disk.** They return a `_figure` (or `_figure_options`)
spec — plain JSON — and `render.py` is the only module that writes files. That
is what keeps the generators testable at thousands of seeds per second and what
lets a spec be re-rendered later as SVG or a web preview.

**Both builders now carry images.** `build_paper.py` renders `q["image"]` under
the stem and `q["option_images"]` beside each label (suppressing text options);
`build_paper_format2.py` had NO image support until 2026-09-16 and silently
dropped every figure — it now renders both, sized smaller because the figure
sits inside a table cell rather than a page column.

**Option-image questions still carry text options.** They are placeholders
(`(चित्र A)`..`(चित्र D)`) that exist so the answer-letter range is well defined
and so a builder that cannot draw still emits something. They are never printed
when the images render.
