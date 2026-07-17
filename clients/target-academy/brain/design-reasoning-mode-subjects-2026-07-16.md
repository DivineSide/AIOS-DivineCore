# Design — Reasoning-Mode Subjects (Maths, Reasoning, Grammar) — 2026-07-16

## Background

Today's ingestion review (हरदेव बाहरी, hindi_vyakaran) surfaced that grammar
doesn't fit the fact-grounding architecture — see `decisions.md` 2026-07-16.
This generalizes: **maths and reasoning already work this way** (no corpus,
self-verified); grammar should join them, not get its own bespoke path.
This doc scopes that as one piece of architecture, not three one-offs.

## 1. One subject-mode flag, not three pipelines (Mayank: agreed)

Add a mode to the subject config (`blueprint.py` / `SUBJECT_MIX`):

```
subject_type: "grounded" | "reasoning"
```

- **`grounded`** (history, GK, UK-specific, economy, polity, …) — unchanged.
  `_slot_context` retrieves `book_passages`, drafting cites the material,
  `ground.check` verifies against it, agentic re-retrieval on a miss.
- **`reasoning`** (maths, reasoning, grammar) — new branch in `_gen_slot`:
  - **no `book_passages` retrieval** — skip the fact-fetch step entirely.
  - **PYQ/style bank is the ONLY input** — `pyq_rag_lookup` supplies real
    question examples (phrasing, difficulty, distractor style) to imitate.
    This is the same call that already feeds `examples` for grounded
    subjects — reasoning-mode subjects just don't ALSO get `passages`.
  - **drafting model reasons the answer itself** (rule application / calc),
    same as maths already does.
  - **grounding gate replaced by a reasoning-check** (see §3) — no passages
    to quote, so `ground.check`'s current contract doesn't apply as-is.

One branch point in `_gen_slot`, keyed off `subject_type` — not a parallel
`_gen_slot_reasoning` function, to avoid drift between the two paths over
time (retry logic, seeding, format handling should stay shared).

## 2. PYQ/MCQ quality bar — CLIENT CONVERSATION (Mayank: this is what we'll
   cover with the client)

For grounded subjects, a mediocre PYQ chunk is low-risk — it only shapes
style, facts still come from `book_passages`. For reasoning-mode subjects,
**the PYQ pattern is the only quality signal there is** — a malformed or
wrong PYQ directly teaches the model a bad pattern. So this tier needs its
own bar, separate from the general PYQ pool.

Questions for the client (folds into the existing
`client-session-2026-07-13-questions.md` discovery, section 5 "PYQ corpus"):

- Does the institute have a **curated** set of grammar/maths/reasoning MCQs
  they'd stake their name on (not just "any PYQ we scraped")?
- Per reasoning subject, how many good examples do we realistically have —
  is it enough to be a real style bank, or does it need building up?
- Any known-bad patterns to explicitly exclude (e.g. a PYQ set with a
  wrong answer key, or a format they don't want imitated)?

Until that conversation happens, treat any existing hindi_vyakaran-style MCQ
banks as **candidate** PYQ-pool material — do not wire them in as the live
style bank without the quality-bar conversation happening first.

## 3. Verification — self-check, but not self-JUDGING

No passages to quote-and-verify against (grounded gate's whole contract).
Replacement: the drafting model's **own worked reasoning** becomes the thing
that gets checked — same shape as the current maths self-verification
(worked `solution` = proof), but with an independent judge reading that
reasoning for correctness, not the drafter re-checking itself.

**Judge must not be the drafter** (same rule as fact-grounding: judge ≠
drafter). Mayank's read on NVIDIA (confirmed 2026-07-16), split by subject —
**this split is intentional, not an oversight**:

### Maths & reasoning — NVIDIA can replace Sarvam for BOTH roles

Mayank is confident here: an NVIDIA-hosted free-tier model (key already in
`.env` — `build.nvidia.com`: Llama 3.1/3.3, Nemotron, Qwen, DeepSeek variants)
can likely **replace Sarvam entirely** for maths/reasoning — both drafting
AND verification. This is a bigger move than "add a third judge option": if
it holds up, maths/reasoning stop depending on Sarvam at all, which also
sidesteps Sarvam's known JSON-reliability problem (it failed as a grounding
judge earlier specifically because it doesn't emit clean structured output
reliably — a reasoning model that "thinks" into a hidden field). Still
needs the test protocol below before it's load-bearing; "confident it can
work" is the hypothesis, not yet the validated result.

### Grammar — NVIDIA is NOT trusted as verifier (Mayank explicitly unsure)

Different call, and intentionally so: Mayank was never confident NVIDIA's
general-purpose free models are strong enough at native Hindi grammar
judgment (sandhi/samas/vilom correctness is a narrower, more
language-specific competence than arithmetic/logic). **Do not default NVIDIA
into the grammar-judge role** just because it's cheap and already
in-hand — grammar's judge model is a SEPARATE open question, most likely
gpt-5.4-nano (already proven as a judge elsewhere) or another candidate,
to be tested on its own merits for THIS specific judgment task.

### Test protocol (same rigor as the nano grounding validation, applied per-subject)

| Subject | Drafter candidate | Judge candidate | What to verify |
|---|---|---|---|
| Maths | NVIDIA model (replaces Sarvam) | NVIDIA (different model) or nano | Does drafting produce correct worked solutions reliably? Does the judge catch a wrong calculation, not just malformed JSON? |
| Reasoning | NVIDIA model (replaces Sarvam) | NVIDIA (different model) or nano | Same, for logic/pattern questions. |
| Grammar | Sarvam (unchanged — Hindi-native) | **NOT NVIDIA by default** — nano or TBD | Does the candidate judge reliably catch a wrong sandhi/samas classification, not just "is this fact quoted"? Narrower, more Hindi-specific than the maths case. |

Build a 30-50 case set of correct/incorrect reasoning PER SUBJECT (don't
reuse one generic set across all three — the judgment task differs enough
that a model good at catching bad arithmetic may not catch bad sandhi, and
vice versa), hand-grade each candidate, only promote to production if it
matches or beats nano's demonstrated grounding-judge reliability (46/50).

## 4. Distractors are naturally easier here (Mayank: agreed)

For grounded subjects, distractors need to be "plausible but wrong" facts —
hard to generate well without risking a distractor that's ITSELF true.
For reasoning-mode subjects, wrong options are **common-mistake patterns**
(wrong sandhi type applied, off-by-one arithmetic, a near-miss antonym) —
these are well-known error classes the PYQ bank already demonstrates, and
the model doesn't need external facts to generate a plausible wrong option,
just knowledge of where students typically slip. Likely LESS prompt
engineering needed here than for the grounded-subject distractor rules.

## Open / not decided

- Exact `subject_type` config shape and where it's declared (blueprint.py
  vs. a new small config table) — pick when implementing, not now.
- Whether grammar needs subject-specific format contracts beyond what
  `formats.py` already has (सन्धि-विच्छेद, विलोम, वाक्य-शुद्धि may need new
  entries) — likely yes, scope during implementation.
- Judge model choice (§3) — explicitly deferred pending the test protocol.
- PYQ quality bar (§2) — explicitly deferred pending the client conversation.

## Sequencing

This is a design pass, not committed to be built next. Suggested order once
picked up: (1) client conversation on PYQ quality (§2) — informs how much
usable style-bank material actually exists per subject before building
anything; (2) judge-model bake-off (§3) using the same rigor as the nano
validation; (3) implement the `subject_type` branch once both are answered.
