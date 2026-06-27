# AI Generative Endpoint — Shubham Handoff

## Division of work

**Shubham owns everything in this doc** — all code, all files, the full endpoint, the ingest script, the wiring. Build it to production-ready. Deploy it. The endpoint should be fully functional on the server.

**Mayank owns the vector database** — creating the `pyq_chunks` table in Supabase and running the ingestion script (`ingest_pyq.py`) to load the PYQ PDFs. He does this separately on his own timeline.

**The key point:** the code and the database are completely independent. Nothing in the code depends on the database having data in it to build and deploy. Build the full endpoint. Once Mayank runs the ingestion and the table has data, `POST /api/generate` goes live automatically — no further code changes needed. That is the goal: Mayank wakes up, runs the ingestion, opens the console, and AI Generative works end to end.

---

## What this endpoint does

Teacher picks a subject + enters a question count → backend generates N exam questions
from the embedded book corpus → runs the existing build pipeline → returns the same
3 output files as `/api/full` (paper .docx, class deck .pptx, answer key .pdf).

---

## The 4-phase flow

**Phase 1 — PYQ topic extraction (Haiku)**
- Fetch 15–20 random PYQ examples for the subject from `pyq_chunks` table (no embedding needed — just `WHERE subject = ? ORDER BY RANDOM() LIMIT 20`)
- Call `claude-haiku-4-5-20251001` with those examples
- Prompt: "What distinct topics/concepts do these exam questions test? Return N/5 topic strings as a JSON array."
- Output: `["उत्तराखंड के प्रथम राज्यपाल", "चिपको आंदोलन", ...]`

**Phase 2 — Topic → book content (RAG, no LLM)**
- For each topic string, call `rag_lookup(stem=topic, top_k=3, threshold=0.25)` from `clients/target-academy/rag/query.py`
- This hits the `book_chunks` table (12,328 records of embedded book content)
- Collect all returned chunks, deduplicate by `book + topic`
- Track which chunk each topic came from — you'll need this for the `sources` field

**Phase 3 — Generate questions (Sonnet)**
- Feed all collected chunks to `claude-sonnet-4-6` as context
- One API call, returns exactly N questions as a JSON array
- System prompt is below — do not change the output schema section

**Phase 4 — Build (existing pipeline, zero new code)**
- Feed the questions list into existing `build_task` (already in `worker/tasks.py`)
- Same outputs as `/api/full`

---

## System prompt for Phase 3

```
You are an Indian competitive-exam question writer for UKSSSC, UPPSC, and similar
state PSC papers.

You have been given excerpts from official study material for the subject: "{subject}".
Generate exactly {count} multiple-choice questions based ONLY on information present
in these excerpts. Do not invent facts.

RULES:
- Language: Hindi (Devanagari). English proper nouns stay in English.
- Each question: exactly 4 options (a), (b), (c), (d)
- Difficulty mix: 30% easy, 50% medium, 20% hard
- No repeated concepts across questions
- Distractors must be plausible — not obviously wrong
- For numerical/reasoning questions: include a worked solution in the "solution" field

OUTPUT: Return ONLY a valid JSON array, no prose, no markdown fences:
[
  {
    "n": 1,
    "stem": "question text in Hindi",
    "options": ["option a text", "option b text", "option c text", "option d text"],
    "answer": "a",
    "reason": "≤160 chars justification"
  }
]

STUDY MATERIAL:
{chunks}
```

---

## New files to create

### `clients/target-academy/rag/ingest_pyq.py`
Ingests PYQs from `corpus/pyq/` into the `pyq_chunks` table.
Mirror the structure of `ingest.py` — same embedding model (`text-embedding-3-small`),
same DB connection pattern (`SUPABASE_DB_URL`). Chunk by question (not sliding window).

### `DsideOS/worker/generate.py`
The generation logic — keeps `tasks.py` clean. Expose one async function:
```python
async def generate_questions(subject: str, count: int) -> list[dict]:
    # Phase 1: pyq_lookup → Haiku → topics list
    # Phase 2: rag_lookup per topic → book chunks
    # Phase 3: Sonnet → questions JSON
    # Returns list[dict] matching Question schema
```

---

## Files to modify

### `clients/target-academy/rag/query.py`
Add `pyq_lookup(subject, top_k)` — random fetch from `pyq_chunks`:
```python
async def pyq_lookup(subject: str, top_k: int = 20) -> list[dict]:
    # SELECT chunk_text, source_file FROM pyq_chunks
    # WHERE subject = %s ORDER BY RANDOM() LIMIT %s
```

Also add subject filtering to existing `rag_lookup()`:
```python
async def rag_lookup(stem, options=None, top_k=5, threshold=0.25, subject=None):
    # add WHERE subject = %s if subject is not None
```

### `DsideOS/worker/tasks.py`
Add `generate_task`:
```python
@shared_task(bind=True, name="worker.tasks.generate")
def generate_task(self, job_id: str, subject: str, count: int, meta: dict):
    jobs.update_meta(job_id, status="RUNNING", stage="generate")
    # call generate.generate_questions(subject, count)
    jobs.update_meta(job_id, stage="build")
    # call _run_builders(job_id, data, font) — existing function
```

Also add RAG path to sys.path (same pattern as pipeline path already there):
```python
RAG = REPO_ROOT / "clients" / "target-academy" / "rag"
sys.path.insert(0, str(RAG))
```

### `DsideOS/api/main.py`
Add endpoint:
```python
@app.post("/api/generate", response_model=JobAccepted)
def generate(
    subject: str = Form(...),
    count: int = Form(...),
    paper_name: str = Form("Paper"),
    format: str = Form("format-1"),
    font: str = Form("krutidev"),
    title_hindi: str = Form(""),
    subtitle_hindi: str = Form(""),
):
    meta = {
        "paper_name": paper_name,
        "format": format,
        "font": font,
        "title_hindi": title_hindi,
        "subtitle_hindi": subtitle_hindi,
    }
    job_id = jobs.new_id()
    jobs.create(job_id, workflow="generate", subject=subject, **meta)
    generate_task.apply_async(args=[job_id, subject, count, meta], task_id=job_id)
    return JobAccepted(job_id=job_id)
```

---

## Subject values (what the frontend sends)

| Frontend label | API value |
|----------------|-----------|
| UK History | `uk-history` |
| UK Geography | `uk-geography` |
| UK Culture | `uk-culture` |
| UK General Studies | `uk-general-studies` |
| General GK | `general-gk` |
| Hindi | `hindi` |

---

## Database tables

**`pyq_chunks`** — Mayank creates this table and runs the ingestion. You do NOT touch this.
The SQL is already written at `clients/target-academy/rag/migrations/001_create_pyq_chunks.sql`.
Your code (`ingest_pyq.py`, `pyq_lookup()`) just needs to read/write to it — the table
will exist by the time you need to test. Until it has data, `POST /api/generate` will
return 0 topics in Phase 1 and gracefully fall back (handle this: if no PYQs found,
skip Phase 1 and go straight to Phase 2 with a generic topic derived from the subject name).

**`book_chunks`** — already exists, 12,328 records of embedded book content. Your `rag_lookup()` calls hit this. It is live and fully populated right now — you can test Phase 2 and Phase 3 immediately without waiting for Mayank's ingestion.

---

## Job stages the frontend will see

```
QUEUED → RUNNING (stage: "generate") → RUNNING (stage: "build") → DONE
```

Frontend already polls `GET /api/jobs/{id}` and shows the stage — no frontend changes needed.

---

## How to test end-to-end

```bash
# 1. Submit a generate job
curl -X POST https://dsideos.divinesideai.com/api/generate \
  -F "subject=uk-history" \
  -F "count=10" \
  -F "paper_name=UK History Test"

# 2. Poll until DONE
curl https://dsideos.divinesideai.com/api/jobs/{job_id}

# 3. Download output
curl -O https://dsideos.divinesideai.com/api/files/{job_id}/UK%20History%20Test.docx
```

Check the output `.docx` — 10 questions, formatted, in Hindi.
Check `questions.json` in the job outputs — every question has `answer` and `sources`.

---

## Environment variables needed

Same as what's already in the server `.env`:
- `ANTHROPIC_API_KEY` — for Haiku (Phase 1) and Sonnet (Phase 3)
- `OPENAI_API_KEY` — for embeddings in Phase 2
- `SUPABASE_DB_URL` — for both `pyq_chunks` and `book_chunks` queries

No new secrets needed.
