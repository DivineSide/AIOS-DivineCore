# -*- coding: utf-8 -*-
"""Celery tasks — the format-agnostic content pipeline, wrapped for async.

Each task mirrors one product workflow from the spec:

    extract_task    ANY input file (docx/pdf/png/jpg) -> universal questions JSON
    build_task      questions JSON + format + font     -> paper + deck (+ answer key)
    answer_key_task questions JSON + font              -> answer-key PDF (standalone)
    solutions_task  questions JSON + mode + font       -> teacher solution doc
    full_task       upload -> extract -> all deliverables (one shot)

The heavy lifting is the existing pipeline modules — these tasks only orchestrate:
detect the input format, route to the right extractor, run the builders, and
record the output manifest. Nothing about a specific paper is hardcoded.
"""
import json
import os
import sys
from pathlib import Path

from celery import shared_task

from . import jobs
from .celery_app import celery_app  # noqa: F401  (registers the app)
from .settings import settings

# Make the Target Academy pipeline importable. (When this generalises beyond one
# client, the pipeline moves into DsideOS; for now we import it in place.)
REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE = REPO_ROOT / "clients" / "target-academy" / "pipeline"
sys.path.insert(0, str(PIPELINE))

# Ensure the LLM key is available to the pipeline's llm.py loader.
if settings.ANTHROPIC_API_KEY:
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.ANTHROPIC_API_KEY)

VALID_FONTS = ("krutidev", "unicode")
VALID_FORMATS = ("format-1", "format-2")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


# ── input routing — the format-agnostic core ─────────────────────────────────

def _extract_any(file_path: Path) -> dict:
    """Route ANY supported input file to the right extractor -> questions dict.

    .docx              -> extract_docx (text path, Unicode out)
    .pdf               -> extract_pdf  (auto: digital text vs scanned vision)
    .png/.jpg/.jpeg    -> extract_vision (Claude Vision)
    """
    ext = file_path.suffix.lower()
    if ext == ".docx":
        import extract_docx
        return extract_docx.extract(file_path)
    if ext == ".pdf":
        import extract_pdf
        return extract_pdf.extract(file_path)
    if ext in IMAGE_EXTS:
        import extract_vision
        return extract_vision.extract([file_path])
    raise ValueError(f"Unsupported input format: {ext}")


def _wrap_questions(questions: list[dict], meta: dict) -> dict:
    """Build the universal top-level JSON the pipeline/builders consume."""
    name = meta.get("paper_name", "Paper")
    return {
        "filename": f"{name}.docx",
        "ppt_filename": f"{name} (Class).pptx",
        "solution_filename": f"{name} - Solution (Teacher).docx",
        "answer_key_filename": f"{name} - Answer Key.pdf",
        "title_hindi": meta.get("title_hindi", name),
        "subtitle_hindi": meta.get("subtitle_hindi", ""),
        "solution_title": meta.get("solution_title", f"{name} - Solution"),
        "solution_subtitle": meta.get("solution_subtitle", ""),
        "format": meta.get("format", "format-1"),
        "font": meta.get("font", "krutidev"),
        "answer_source": meta.get("answer_source"),
        "questions": questions,
    }


def _placeholder_answers(data: dict) -> None:
    """When no answer key is provided, give every unanswered question a neutral
    placeholder so the builders run, and flag it for review."""
    for q in data["questions"]:
        if not q.get("answer"):
            q["answer"] = "a"
            q["flag"] = "उत्तर कुंजी उपलब्ध नहीं"


def _run_builders(job_id: str, data: dict, font: str) -> list[dict]:
    """Write the questions JSON into the job's input dir, run run_pipeline.run()
    pointed at the job's output dir, return the output manifest."""
    import run_pipeline

    qjson = jobs.input_dir(job_id) / "questions.json"
    qjson.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Point the pipeline's output at THIS job's folder (it defaults to the
    # client's review/output). We override the module-level OUTPUT_DIR.
    run_pipeline.OUTPUT_DIR = jobs.output_dir(job_id)
    run_pipeline.run(qjson, font=font)
    return jobs.list_outputs(job_id)


# ── tasks ─────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name="worker.tasks.extract")
def extract_task(self, job_id: str):
    """W: any input file -> universal questions JSON (Unicode)."""
    jobs.update_meta(job_id, status="RUNNING", stage="extract")
    try:
        src = next(jobs.input_dir(job_id).iterdir())
        result = _extract_any(src)
        out = jobs.output_dir(job_id) / "questions.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        jobs.update_meta(job_id, status="DONE", outputs=jobs.list_outputs(job_id),
                         n_questions=len(result.get("questions", [])))
        return {"status": "DONE", "n_questions": len(result.get("questions", []))}
    except Exception as e:
        jobs.update_meta(job_id, status="FAILED", error=f"{type(e).__name__}: {e}")
        raise


@shared_task(bind=True, name="worker.tasks.build")
def build_task(self, job_id: str, questions: list[dict], meta: dict):
    """W1: questions JSON + format + font -> paper + deck + answer key."""
    font = (meta.get("font") or "krutidev").lower()
    jobs.update_meta(job_id, status="RUNNING", stage="build", font=font,
                     format=meta.get("format", "format-1"))
    try:
        data = _wrap_questions(questions, meta)
        _placeholder_answers(data)
        outputs = _run_builders(job_id, data, font)
        jobs.update_meta(job_id, status="DONE", outputs=outputs)
        return {"status": "DONE", "outputs": outputs}
    except Exception as e:
        jobs.update_meta(job_id, status="FAILED", error=f"{type(e).__name__}: {e}")
        raise


@shared_task(bind=True, name="worker.tasks.answer_key")
def answer_key_task(self, job_id: str, questions: list[dict], meta: dict):
    """W3: questions JSON + font -> standalone answer-key PDF."""
    import build_answer_key

    font = (meta.get("font") or "krutidev").lower()
    jobs.update_meta(job_id, status="RUNNING", stage="answer_key", font=font)
    try:
        data = _wrap_questions(questions, meta)
        qjson = jobs.input_dir(job_id) / "questions.json"
        qjson.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        name = meta.get("paper_name", "Paper")
        out = jobs.output_dir(job_id) / f"{name} - Answer Key.pdf"
        build_answer_key.build(qjson, out, font=font)
        jobs.update_meta(job_id, status="DONE", outputs=jobs.list_outputs(job_id))
        return {"status": "DONE", "outputs": jobs.list_outputs(job_id)}
    except Exception as e:
        jobs.update_meta(job_id, status="FAILED", error=f"{type(e).__name__}: {e}")
        raise


@shared_task(bind=True, name="worker.tasks.solutions")
def solutions_task(self, job_id: str, questions: list[dict], meta: dict):
    """W2: questions JSON + font (+ generate explanations) -> teacher solution doc.

    If meta["generate_explanations"] is true, run generate_solutions first to
    populate q["solution"] (EXPLAIN mode if answers given, else FIND+EXPLAIN).
    Then build the solution doc.
    """
    import build_solution

    font = (meta.get("font") or "krutidev").lower()
    jobs.update_meta(job_id, status="RUNNING", stage="solutions", font=font)
    try:
        data = _wrap_questions(questions, meta)
        if not any(q.get("answer") for q in data["questions"]):
            data["answer_source"] = None
        else:
            data.setdefault("answer_source", "official_key")

        qjson = jobs.input_dir(job_id) / "questions.json"
        qjson.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        if meta.get("generate_explanations"):
            jobs.update_meta(job_id, stage="generate_explanations")
            import generate_solutions
            gen_data = json.loads(qjson.read_text(encoding="utf-8"))
            official = gen_data.get("answer_source") == "official_key"
            import anthropic
            client = anthropic.Anthropic()
            for q in gen_data["questions"]:
                if q.get("solution"):
                    continue
                if official:
                    res = generate_solutions.call_explain(client, q)
                    generate_solutions.apply_explain(q, res)
                else:
                    res = generate_solutions.call_find_and_explain(client, q)
                    generate_solutions.apply_find(q, res)
            qjson.write_text(json.dumps(gen_data, ensure_ascii=False, indent=2),
                             encoding="utf-8")

        name = meta.get("paper_name", "Paper")
        out = jobs.output_dir(job_id) / f"{name} - Solution (Teacher).docx"
        build_solution.build(qjson, out, font=font)
        jobs.update_meta(job_id, status="DONE", outputs=jobs.list_outputs(job_id))
        return {"status": "DONE", "outputs": jobs.list_outputs(job_id)}
    except Exception as e:
        jobs.update_meta(job_id, status="FAILED", error=f"{type(e).__name__}: {e}")
        raise


@shared_task(bind=True, name="worker.tasks.full")
def full_task(self, job_id: str, meta: dict):
    """One-shot: uploaded file -> extract -> all deliverables in chosen format/font."""
    font = (meta.get("font") or "krutidev").lower()
    jobs.update_meta(job_id, status="RUNNING", stage="extract", font=font,
                     format=meta.get("format", "format-1"))
    try:
        src = next(jobs.input_dir(job_id).iterdir())
        extracted = _extract_any(src)
        jobs.update_meta(job_id, stage="build",
                         n_questions=len(extracted.get("questions", [])))

        data = _wrap_questions(extracted["questions"], meta)
        _placeholder_answers(data)
        outputs = _run_builders(job_id, data, font)
        jobs.update_meta(job_id, status="DONE", outputs=outputs,
                         n_questions=len(extracted.get("questions", [])))
        return {"status": "DONE", "outputs": outputs}
    except Exception as e:
        jobs.update_meta(job_id, status="FAILED", error=f"{type(e).__name__}: {e}")
        raise


@shared_task(name="worker.tasks.cleanup_jobs")
def cleanup_jobs():
    """Beat task: purge job folders past their TTL."""
    return jobs.cleanup_expired(settings.JOB_TTL_HOURS)
