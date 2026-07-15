---
name: harness-engineering
description: Use this skill whenever designing, reviewing, or debugging the system around an AI model call — regardless of whether that system is a RAG pipeline, web scraper, classifier, backend automation, or any other AI-powered product. Covers what to feed into the model, how to verify its output, how to gate the actions it triggers, and how to persist state across calls. Trigger this whenever the user is architecting a new AI feature, debugging unreliable model-driven behavior, adding self-tuning/auto-improvement logic, designing multi-step or multi-call pipelines, or asking how to make an AI system more reliable, safe, or production-ready — even if they don't use the word "harness." Do NOT use this for pure prompt-wording questions with no surrounding system (single one-off prompt requests) — that's prompt engineering, not harness engineering.
---

# Harness Engineering

A harness is everything around a model call that isn't the model itself: what goes into it, what happens to what comes out, what it's allowed to trigger, and what persists after it's done. The model is the only genuinely hard-to-control part of the system — everything in this skill is about controlling the parts you *can* control, so that the whole system is reliable even when any single model call isn't.

**Harness engineering is steering the model through a workflow with more control than a prompt can ever give.** Left to "figure it out" with just good context and a good prompt, a model will still make mistakes — confidently, silently, and differently each run. The harness restricts it to calculated decisions inside boundaries that code enforces. You are not trusting the model less; you are asking it for less, and building more.

**Core framing:** every AI system, no matter what it does, reduces to four checkpoints:

```
  INPUT  →  MODEL CALL  →  OUTPUT CHECK  →  ACTION GATE  →  STATE
    ^                                                          |
    |__________________________________________________________|
```

1. **Input** — what does the model see for *this* call?
2. **Output check** — is the model's output actually correct/usable?
3. **Action gate** — what is this output allowed to cause, and under what conditions?
4. **State** — what gets written down afterward, so the next call (or next run) isn't starting blind?

Almost every reliability problem in an AI system traces back to skipping one of these four. Use them as a diagnostic checklist as much as a design checklist.

## The Enforcement Ladder

The single most important design decision, for every rule your system must obey:
**mechanical discipline > prompt instructions.** For each rule, place it on the
highest rung it can reach — and only what code genuinely cannot do falls through
to the prompt. Prompt is the enforcement of *last* resort, never first.

```
1. IMPOSSIBLE BY CONSTRUCTION   code builds the structure; the error cannot exist
2. DETECTED BY CODE             deterministic validator; failure -> informed retry
3. DETECTED BY A MODEL          cheap second call, blind & narrow, verifying one thing
4. STATED IN THE PROMPT         the judgment residue code can't express
5. SHOWN BY EXAMPLE             taste/style demonstrated via retrieved gold examples
```

- **Rung 1 — make the failure impossible.** Ask the model for the smallest
  *intelligent* unit and let code assemble everything mechanical around it. A
  matching-question generator that asks the model only for the correct pairs —
  while code builds the option permutations and derives the answer key — cannot
  produce an inconsistent question, ever. An extractor that asks the model only
  for *line numbers* — while code slices the actual text — cannot misspell
  content it never rewrote, and its tiny output cannot truncate. Split every
  task into knowledge (model) and structure (code); move all structure to code.
- **Rung 2 — deterministic detection.** Counts, formats, ranges, plausibility
  (a CE year outside 600–2026), duplicates, shape-consistency of options: all
  pure code, all returning a *specific reason string*, not a boolean.
- **Rung 3 — model-verifies-model,** for checks that need reading comprehension
  (is this claim actually supported by this source passage?). Keep the verifier
  blind to everything except the evidence and the claim, and give it a
  mechanical contract (must quote the supporting sentence, or reject).
- **Rung 4 — prompt the residue.** "Distractors must be genuinely confusing" is
  judgment; no code can grade it. But notice: even fuzzy rules usually have a
  mechanical core you can strip out first — "confusing" is judgment, but
  "3 options are names and 1 is a date, so it's eliminable by kind" is a shape
  check code CAN do. Split every fuzzy rule into its mechanical core (rung 2)
  and its judgment residue (rung 4).
- **Rung 5 — demonstration beats instruction** for style and taste. Retrieving
  two real gold-standard examples of the exact thing being produced steers
  harder than any paragraph describing them. Curate a small bank of excellent
  examples (10–20 per pattern saturates the benefit) rather than hundreds of
  mediocre ones — examples are style teachers, not fact sources.

## How to use this skill

When the user is designing a new AI feature or debugging an unreliable one, walk through the four checkpoints in order and ask, for their specific system:

- **Input**: What does this call need to know that it currently doesn't get? What's currently assumed rather than explicitly passed in? Is the input *known-good*, or merely assumed good?
- **Output check**: Is there anything verifying this output against reality, or is it trusted at face value? Could it be verified automatically, or does it need a human glance?
- **Action gate**: Does the model's output directly cause something (send, write, delete, spend, notify)? Is there a check in between the decision and the action?
- **State**: If this call is part of a sequence, what does the *next* call need to know, and where does that live — is it a durable record, or is it just hoping the model "remembers"?

Then, for every rule the system must obey, place it on the Enforcement Ladder — as high as it can go. Don't apply all principles mechanically — most real systems only have weak spots at one or two of the four checkpoints. Find which one is actually broken before prescribing fixes.

## The principles

### 1. Input: the model only knows what's in this call
A model has no memory of a different call, a different session, or a different stage of your pipeline unless it's physically in the prompt you send this time. Whatever the model needs to make a good decision — prior results, current state, the specific rule to follow — must be explicit input, not assumed context. Concretely: if a scoring step must not re-flag something already rejected, that rejection has to be *in* this call's input, not something you hope carries over.

### 2. Input: one narrow job per call
A call asked to do several loosely-related things at once tends to do all of them worse, or silently skip the least obvious one. A call asked one specific, bounded thing is both more reliable and much easier to check. If a task has real stages, that's a signal to split it into multiple calls (or a short explicit chain), not to cram it into one instruction. Narrow calls have a second payoff: **structural guarantees.** One-topic-per-call makes topic drift *impossible*, where "cover diverse topics" in one big call merely makes it discouraged.

### 3. Input: measure the input's quality — starved or corrupt context produces confident garbage
When a model underperforms, check what it was actually *given* before touching the prompt. A generator fed one usable fact per call will hallucinate the rest — that's compensation, not disobedience. Worse: **a verification gate is only as honest as its ground truth** — a grounding check run against corrupted source text will *defend* the corruption. So gate the inputs themselves: deterministic health checks on the corpus/data at ingest time (impossible values, damage signatures, fragment rates), run after every ingest, so "who knows how much of the data is bad?" is always a one-command answer. And derive tuning numbers (quotas, mixes, thresholds) from *measured* data distributions, not from conviction.

### 4. Output: never trust output at face value
Models don't reliably signal uncertainty — they produce confident output whether it's right or wrong. Every system needs *something outside the model* checking the output against reality: does this extracted field match the source, does this citation actually exist in the document, does this classification meet a confidence bar. If there's no automatic way to check, that's the signal for a human-review step, not a reason to skip checking.

### 5. Output: retry informed, never blind — and diagnose the failure class first
A failed output retried with the identical prompt mostly fails identically. Feed the *specific* failure reason back into the retry ("option 4 is missing — it may be on the next line"; "this fact is not in the source — use only stated facts") and the model corrects instead of re-guessing; most informed retries succeed on the next attempt. But first diagnose *which kind* of failure it is — different failure classes need different retries (re-asking a boundary question is useless when the boundary was right and the parsing failed), and retrying the wrong class burns money to reproduce the same failure. Bound the loop (2–3 attempts), then hit a **designed terminal state**: ship the best effort with the *deliverable kept clean* (no error flags on user-facing output) while recording the failure out-of-band for the operator (job metadata, dashboard). Best-effort-after-a-forced-correction-loop is honest; best-effort-on-the-first-silent-guess is the fallacy.

### 6. Output: when the model must rewrite content, cage the rewrite with a diff-guard
Sometimes the model's job *is* to modify text (proofreading, normalizing, translating). Trust the prompt's "only fix spelling" rule with code, not hope: mechanically diff the output against the input and reject any change outside the permitted dimension — numbers changed, foreign tokens changed, length ratio beyond a spelling-fix's reach. Rejected corrections keep the original (fail-safe: a fact is never corrupted by its own cleanup step).

### 7. Output: capture *why* something failed, not just *that* it failed
Two failures can look identical on the surface (empty output, wrong format, timeout) while having completely different causes. If failures are logged to improve the system later, the log needs enough detail to tell causes apart — otherwise the same category of failure gets "fixed" repeatedly without ever being resolved.

### 8. Action: gate every consequential action behind a check
Whatever the model decides — send, tag, flag, delete, spend — that decision should pass through a separate check before it executes, not fire straight from the model's output. The model proposes; a separate piece of logic (a rule, a permission list, a confidence threshold) disposes. This is true no matter how good the model has been so far — the gate exists for the run where it isn't.

### 9. Action: decide human checkpoints on purpose, not evenly
Don't review everything (too slow, no real safety benefit beyond a point) or nothing (the expensive mistakes go uncaught). Identify the specific points where a wrong action is costly or hard to reverse — external-facing sends, spending, deletion — and put a deliberate checkpoint there. Let everything else run without friction.

### 10. State: persistent memory lives outside the model, not inside its "memory"
Don't rely on a model to carry a growing history in its own context across calls. Write the actual state down — a record, a row, a log entry — and feed back only the relevant part next time. This is also what makes a system debuggable: you can inspect exactly what happened without re-running or re-asking the model to explain its own past behavior. Long-running pipelines get the same treatment at the job level: **checkpoint completed units of work** so a mid-run failure (quota exhaustion, credit dry-out, network drop) resumes where it stopped instead of restarting — and classify errors so the run rotates/retries on the recoverable ones (rate limits, transient disconnects) and stops loudly on the rest.

### 11. State: cross-item invariants need shared state — and that's your only concurrency constraint
Some rules span outputs, not single outputs: no duplicate entities across a generated set, no re-processing of an already-handled record. These need a guard object holding the run's state — and that guard is usually the *only* thing serializing your pipeline. Parallelize everything independent (each unit's retrieve→generate→verify chain) in waves, and reconcile with the shared guard sequentially at wave boundaries; a rare collision re-runs *informed* with the collision as its feedback. Full speedup, zero gates skipped.

### 12. State: any self-tuning change needs a two-sided check before it sticks
If any part of the system adjusts its own behavior based on performance (a prompt, a rule, a routing decision — manually or automatically), don't keep a change just because it improved the one metric it was tested against. Check two things: did it fix the targeted problem, *and* did it break anything that was previously working. Only keep changes that pass both — this is the single most common thing that's skipped when people add "self-improving" logic, and skipping it is how systems quietly get worse while their one watched metric goes up.

### 13. State: the measurement is what the system will actually learn to satisfy
Whatever you use to judge success — a keyword match, a second model's approval, a benchmark score — is exactly what gets optimized, including in dumb or gameable ways. Keep whatever's doing the grading separate from, and blind to, the part being improved.

## Quick diagnostic

If someone describes a misbehaving AI system, map the symptom to a checkpoint:

| Symptom | Likely checkpoint |
|---|---|
| "It doesn't know about X" / repeats past mistakes | Input (1) or State (10) |
| Output tries to do too much / misses part of the ask | Input (2) |
| Hallucinated facts, generic/shallow output | Input (3) — check what it was *given* before blaming the model |
| Verifier keeps approving wrong facts | Input (3) — the verifier's ground truth is corrupt |
| Wrong-but-confident output slipping through | Output (4) |
| Retries fail the same way every time | Output (5) — blind retry, or wrong failure class |
| A "cleanup" step corrupted real content | Output (6) — rewrite without a diff-guard |
| Same bug keeps getting "fixed" and coming back | Output (7) |
| Structurally broken output (mismatched keys/counts/answer) | Enforcement Ladder rung 1 — the model is building what code should build |
| A bad decision actually executed (sent, deleted, spent) | Action (8) or (9) |
| Long batch job dies mid-run and restarts from zero | State (10) — no unit checkpoints, no error classes |
| Duplicates/conflicts appear only under parallelism | State (11) — shared invariant not reconciled |
| System "improved" a metric but got worse in practice | State (12) or (13) |

## The one-line summary

Steer with structure, verify with code, retry with information, prompt only the
residue — and make the numbers come from measurements, not vibes.
