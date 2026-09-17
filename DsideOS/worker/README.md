# worker/ — the Celery job runtime and the question generator

Two things live here, and they are only loosely related:

1. **Job plumbing** — Celery tasks, on-disk job storage, settings, tracing.
   This runs the *content pipeline* (upload → extract → build a paper).
2. **Question generation** — the AI-generative engine plus the code-only
   reasoning generators. This is what `generate_task` calls.

The document builders themselves are **not** here; they are in `pipeline/`.
`tasks.py` is the seam between the two.

---

## Job plumbing

| file | responsibility |
|---|---|
| `__init__.py` | Empty. Exists only so `worker` is a package (`from . import generate`). |
| `celery_app.py` | Builds the Celery app (own Redis broker/backend), registers the beat schedule, boots `tracing` on worker start. |
| `settings.py` | Pydantic-settings config from env/`.env` — `JOBS_DIR`, retention, API keys. Defines `DSIDEOS_ROOT`. |
| `jobs.py` | On-disk job store: `job_dir` / `input_dir` / `output_dir`, atomic `meta.json`, lifecycle + progress, retention expiry, stuck-job reaping. **`input_dir(job_id)` is where `questions.json` and any generated figures live** — and it is what `build_paper` resolves image paths against. |
| `tasks.py` | The Celery tasks (`extract`, `build`, `answer_key`, `solutions`, `full`, `generate`, plus two beat tasks). Routes inputs to extractors, then hands off to `pipeline/run_pipeline`. |
| `tracing.py` | Optional OpenTelemetry/Phoenix bootstrap. **Off by default** (`PHOENIX_TRACING_ENABLED=0`). |
| `Dockerfile` | The production image: LibreOffice (docx→pdf), Devanagari fonts, bundled licensed fonts, then `requirements.txt`. **Only `worker/requirements.txt` is installed** — anything not listed there does not exist in production. |

## LLM generation path

| file | responsibility |
|---|---|
| `generate.py` | The orchestrator. `generate_questions_batched(subject, count, …)` and `generate_exam(exam, total)`. Also holds provider selection (Groq/OpenAI), Hindi subject labels, section selection, drafting, and the top-up loop. |
| `batch_gen.py` | Builds the one-call-per-subject prompt and its strict `json_schema`; two system prompts — `BATCH_SYSTEM` (real passages) and `NORAG_SYSTEM` (taxonomy leaves). Token-aware chunking for Groq's per-request ceiling. |
| `blueprint.py` | Owns every count. Largest-remainder allocation of measured distributions: subjects per exam, formats per subject, difficulty per paper. |
| `formats.py` | Per-format contracts (plain/match/statement/order/assertion). The model returns only FACTS; code assembles the stem block, the कूट grid and the answer letter, so a structurally inconsistent question is impossible. |
| `difficulty.py` | Per-subject prose definitions and worked exemplars of easy/moderate/hard, injected into the prompt. Only the current subject's block goes in. |
| `syllabus.py` | Canonical transcription of the official UKSSSC 2026 syllabus. **Reference data, not a live caller** — the taxonomies were authored FROM it, and it is what you check a taxonomy against. |
| `taxonomy.py` | The no-RAG topic source: samples question-sized syllabus leaves from `taxonomy_data/<family>/<subject>.json`, with a cross-paper reuse cooldown (migration 009). |
| `taxonomy_data/` | 1,354 hand-authored topic leaves across 7 authored subjects, plus 4 **derived** files (`indian-history/-geography/-polity/-economics.json`) carved out of `general-gk.json` by syllabus section. Authored source, not generated — kept here rather than under `corpus/` because `corpus/` is gitignored. **The `indian-*` files are a REGROUPING, not a re-authoring**: same bullets, same leaves. Edit `general-gk.json` and re-derive, or the two drift apart. `general-gk.json` deliberately keeps all 24 bullets (it is what exam mode allocates against), so in subject mode it overlaps the four. |
| `validate_gen.py` | Mechanical gate for LLM output: `validate_question(q)` per question, `PaperGuard` across the paper (stem dedup, entity repeat, numeric budget). |

## Code-only reasoning path

`reasoning/` has its own README — read that one for detail. In short: eleven
text generators plus four figure generators (dice, triangles, clock dials,
figure series) and one that answers with four option diagrams (venn),
**no model call anywhere**, with `tests/test_reasoning.py` as the correctness
gate. Figure specs are rendered to PNGs by `reasoning/render.py`, which writes
into the job's input dir and RAISES on any failure — a figure that fails to
write would otherwise be dropped by `run_pipeline.validate` and ship a short
paper with no error.

---

## Things worth knowing before you change anything here

**`ground.py` is dead on the live path.** Grounding was deliberately removed
from the batched engine (see `generate.py`'s module docstring). The module is
retained and still works — re-enabling is one call — but nothing imports it
today. Do not assume a generated fact has been verified: nothing verifies it.

**`validate_gen.py` does not cover reasoning questions.** That path bypasses it
by design — every check in it is a proxy for an LLM failure mode that cannot
occur when code computes the answer, and two of them (the numeric-answer budget
and the CE-year range) actively rejected correct reasoning questions. See
`reasoning/__init__.py` for the argument.

**`generate.py` is ~1,100 lines doing several jobs** — provider selection,
subject labels, source selection, drafting, top-up, figure rendering, and both
public entry points. It works, but it is the obvious split candidate if this
folder is ever reorganised.

**"reasoning" means three unrelated things in this package**, which is a real
source of confusion:
- `worker/reasoning/` — the code-only question generators
- `reasoning_effort` — a Groq/gpt-oss API parameter (`generate.py`)
- `"reasoning"` — the subject slug (सामान्य बुद्धि परीक्षण एवं तर्कशक्ति)

**Only `worker/requirements.txt` is installed in the image.** matplotlib,
cairo, svglib and reportlab are absent from both the environment and that file,
so figure rendering uses Pillow, which is already a dependency. Adding an
import means adding it there, and it means a bigger image.

**Fonts differ between local and production.** Local Windows has Arial; the
container has Devanagari fonts plus whatever is bundled at
`/usr/share/fonts/truetype/dsideos/`, and **no guaranteed Latin TTF**. Anything
drawing Latin glyphs must resolve fonts through a fallback chain — see
`reasoning/figures.py`.
