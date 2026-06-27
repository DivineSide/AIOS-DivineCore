# DSideOS Content Backend — verified API contract (2026-06-27)

Read straight from the LIVE backend's OpenAPI (`dsideos-api`). This is authoritative.

## Endpoints

### File upload (multipart/form-data)
- `POST /api/extract` — `file*` → `{questions: [...]}`
- `POST /api/full` — `file*` (+ `paper_name`, `format`, `font`, `title_hindi`, `subtitle_hindi`) → full pipeline, returns a job

### JSON (take a questions array)
- `POST /api/build` — `{questions*: Question[], meta?: BuildMeta}`
- `POST /api/answer-key` — `{questions*: Question[], meta?: BuildMeta}`
- `POST /api/solutions` — `{questions*: Question[], meta?: BuildMeta}`

### Jobs / files
- `GET /api/jobs/{job_id}` — job status
- `GET /api/files/{job_id}/{name}` — download an output file

## Types
- **Question**: `{ n*:int, stem*:str, options?:[], answer?, reason?, solution?, sources?:[], flag?, image?, option_images?:[] }`
- **BuildMeta**: `{ paper_name, format, font, title_hindi, subtitle_hindi, solution_title, solution_subtitle, answer_source?, generate_explanations:bool }`

## The big finding
There is **NO topic-based generation endpoint.** The backend only transforms an
**uploaded file** (extract/full) or a **questions array** you already have
(build/answer-key/solutions). So the console's **"AI Generative" mode (type a
topic → get questions) cannot work** until the backend adds a generate endpoint.

## What the console should do
- **Manual / Import** (upload-based): already correct — keep `/api/full` (or use
  `/api/extract` for questions-only).
- **Generative tools that upload a file** (Solutions, Answer Key from a file):
  chain `extract` → then `solutions`/`answer-key` with the returned questions.
- **Generative tools that take a topic** (Full, Questions from a topic):
  **blocked** — backend has no topic generation. Hide/disable, or Mayank adds it.
