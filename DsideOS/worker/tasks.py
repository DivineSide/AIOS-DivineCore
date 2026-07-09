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

# the RAG package (query.py: rag_lookup/pyq_lookup) — used by generate_task.
RAG = REPO_ROOT / "clients" / "target-academy" / "rag"
sys.path.insert(0, str(RAG))

# Ensure the LLM key is available to the pipeline's llm.py loader.
if settings.ANTHROPIC_API_KEY:
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.ANTHROPIC_API_KEY)

VALID_FONTS = ("krutidev", "unicode")
VALID_FORMATS = ("format-1", "format-2")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


# ── input routing — the format-agnostic core ─────────────────────────────────

# a .docx is a zip of XML; python-docx fully inflates it with no size cap, so a
# small "zip bomb" can inflate to many GB and OOM the worker. Reject anything that
# decompresses past this ceiling or with an extreme compression ratio.
_MAX_UNCOMPRESSED_MB = 300
_MAX_ZIP_RATIO = 120


def _check_zip_bomb(path: Path) -> None:
    import zipfile
    try:
        with zipfile.ZipFile(path) as zf:
            comp = sum(i.compress_size for i in zf.infolist()) or 1
            uncomp = sum(i.file_size for i in zf.infolist())
    except zipfile.BadZipFile:
        raise ValueError("Corrupt or invalid .docx file.")
    if uncomp > _MAX_UNCOMPRESSED_MB * 1024 * 1024 or (uncomp / comp) > _MAX_ZIP_RATIO:
        raise ValueError("Document is too large or suspiciously compressed.")


# Sarvam Vision (document OCR) is the DEFAULT extraction path: it reads the doc
# as an image and returns clean Unicode, sidestepping the Kruti-Dev/English
# ambiguity that garbles the legacy .docx text layer. Set USE_SARVAM_VISION=0 to
# force the old text-layer path.
_USE_SARVAM_VISION = os.environ.get("USE_SARVAM_VISION", "1") == "1"

# A native .docx (typed in Word) has an unambiguous text layer that beats image
# OCR on look-alike Devanagari glyphs — prefer it for .docx inputs that carry a
# usable text layer. Set PREFER_DOCX_TEXT_LAYER=0 to force everything through OCR.
_PREFER_DOCX_TEXT_LAYER = os.environ.get("PREFER_DOCX_TEXT_LAYER", "1") == "1"


def _extract_text_layer(file_path: Path) -> dict:
    """The original per-type extractors (text layer / Claude Vision). Used as the
    fallback when Sarvam Vision is unavailable or fails."""
    ext = file_path.suffix.lower()
    if ext == ".docx":
        _check_zip_bomb(file_path)
        import extract_docx
        return extract_docx.extract(file_path)
    if ext == ".pdf":
        import extract_pdf
        return extract_pdf.extract(file_path)
    if ext in IMAGE_EXTS:
        import extract_vision
        return extract_vision.extract([file_path])
    raise ValueError(f"Unsupported input format: {ext}")


_USE_CLAUDE_VISION_FALLBACK = os.environ.get("USE_CLAUDE_VISION_FALLBACK", "1") == "1"


def _claude_vision_extract(file_path: Path) -> dict:
    """Read the doc as page IMAGES via Claude Vision (extract_vision.py). Handles
    docx (-> PDF first) and batches pages under Claude's per-request image cap so
    a long paper doesn't blow the 20-image limit. Raises on failure so the caller
    can drop to the text layer."""
    import extract_vision

    ext = file_path.suffix.lower()
    # Claude Vision reads images/PDFs; a .docx must become a PDF first (same
    # LibreOffice path Sarvam uses).
    if ext == ".docx":
        import extract_sarvam_vision
        pdf = extract_sarvam_vision._docx_to_pdf(file_path)
    else:
        pdf = file_path

    # Batch pages so each request stays within the image cap. extract_vision
    # renders PDF pages internally; to batch, split the PDF into page ranges.
    import fitz
    doc = fitz.open(str(pdf))
    n_pages = doc.page_count
    doc.close()

    cap = max(1, extract_vision.MAX_IMAGES - 2)  # headroom under the hard cap

    def _extract_range(start: int, end: int) -> list[dict]:
        """Extract pages [start, end) via Vision. On a TOKEN-CAP truncation, split
        the range in half and recurse (keeping the questions already salvaged from
        the truncated call) so a dense batch never silently loses its tail."""
        part = fitz.open()
        src = fitz.open(str(pdf))
        part.insert_pdf(src, from_page=start, to_page=end - 1)
        src.close()
        part_path = pdf.with_name(f"{pdf.stem}_cv_{start + 1}-{end}.pdf")
        part.save(str(part_path))
        part.close()
        try:
            return extract_vision.extract([part_path]).get("questions", [])
        except extract_vision.VisionTruncated as tr:
            if end - start <= 1:
                # a single page still overflowed the cap — keep what we salvaged
                print(f"  [claude-vision] page {start + 1} truncated; kept "
                      f"{len(tr.salvaged)} salvaged", file=sys.stderr)
                return tr.salvaged
            mid = (start + end) // 2
            print(f"  [claude-vision] pages {start + 1}-{end} truncated; "
                  f"re-splitting {start + 1}-{mid} / {mid + 1}-{end}", file=sys.stderr)
            return _extract_range(start, mid) + _extract_range(mid, end)

    all_questions: list[dict] = []
    failed_batches, total_batches = 0, 0
    starts = [0] if n_pages <= cap else list(range(0, n_pages, cap))
    for start in starts:
        end = min(start + cap, n_pages)
        total_batches += 1
        try:
            all_questions.extend(_extract_range(start, end))
        except Exception as e:
            failed_batches += 1
            print(f"  [claude-vision] batch pages {start + 1}-{end} failed "
                  f"({type(e).__name__}: {e}); continuing", file=sys.stderr)
    if not all_questions:
        raise RuntimeError("Claude Vision returned no questions")
    # surface a MATERIAL partial failure rather than silently shipping a short paper
    if failed_batches and total_batches and failed_batches / total_batches >= 0.25:
        print(f"  [claude-vision] WARNING: {failed_batches}/{total_batches} page "
              f"batches produced no questions — the paper may be short.",
              file=sys.stderr)
    print(f"  [claude-vision] extracted {len(all_questions)} questions from "
          f"{n_pages} page(s)", file=sys.stderr)
    return {"questions": all_questions, "_failed_batches": failed_batches,
            "_total_batches": total_batches}


def _extract_any(file_path: Path) -> dict:
    """Route ANY supported input file to questions dict.

    DEFAULT: Sarvam Vision OCR -> clean Unicode text -> shared question structuring.
    FALLBACK 1: Claude Vision reads the doc as page IMAGES (clean Hindi, resilient
    when Sarvam is out of credits / errors).
    FALLBACK 2: the legacy text-layer extractors (only if both vision paths fail).
    """
    ext = file_path.suffix.lower()
    if ext == ".docx":
        _check_zip_bomb(file_path)

    # NATIVE .docx SHORT-CIRCUIT: a Word-typed paper carries a real text layer
    # whose characters are unambiguous. Image OCR (Sarvam) reads the rendered
    # glyphs and confuses look-alike Devanagari print shapes (श↔भ: शेखर->भोखर),
    # AND can skip the first question tucked under the cover header. The native
    # text layer has neither problem, so for a .docx WITH a usable text layer it
    # is the source of truth — use it before OCR. Scanned-image .docx wrappers
    # have no usable text layer -> this returns False -> OCR path (correct).
    if ext == ".docx" and _PREFER_DOCX_TEXT_LAYER:
        try:
            import extract_docx
            if extract_docx.has_usable_text_layer(file_path):
                print("  [extract] native .docx with a clean text layer -> "
                      "using it directly (deterministic, no OCR glyph guessing)",
                      file=sys.stderr)
                data = extract_docx.extract(file_path)
                if data.get("questions"):
                    return data
                print("  [extract] text-layer extract yielded no questions; "
                      "falling through to Sarvam Vision", file=sys.stderr)
        except Exception as e:
            print(f"  [extract] docx text-layer path failed "
                  f"({type(e).__name__}: {e}); trying Sarvam Vision",
                  file=sys.stderr)

    if _USE_SARVAM_VISION:
        try:
            import extract_sarvam_vision
            import extract_docx
            text = extract_sarvam_vision.digitize_to_text(file_path)
            data = extract_docx.extract_from_text(text, label=file_path.name)
            if data.get("questions"):
                return data
            print("  [extract] Sarvam Vision yielded no questions; "
                  "trying Claude Vision", file=sys.stderr)
        except Exception as e:
            print(f"  [extract] Sarvam Vision failed ({type(e).__name__}: {e}); "
                  f"trying Claude Vision", file=sys.stderr)

    # FALLBACK 1: Claude Vision (reads the doc as images). Preferred over the
    # text layer because it produces clean Unicode Hindi instead of Kruti-Dev
    # gibberish — this is what runs when Sarvam is out of credits.
    if _USE_CLAUDE_VISION_FALLBACK:
        try:
            data = _claude_vision_extract(file_path)
            if data.get("questions"):
                return data
        except Exception as e:
            print(f"  [extract] Claude Vision failed ({type(e).__name__}: {e}); "
                  f"falling back to text layer", file=sys.stderr)

    return _extract_text_layer(file_path)


def _safe_name(raw: str) -> str:
    """Sanitise a user-supplied paper name into a safe filename stem. The name
    flows into output paths (OUTPUT_DIR / f"{name}.docx"), so a value like
    "../../etc/cron.d/x" must not be able to escape the output dir. Strip path
    separators, drop traversal, and fall back to a default."""
    import re
    base = os.path.basename(str(raw or "")).replace("\\", "").replace("/", "")
    base = base.lstrip(".").strip()
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", base)  # also drop Windows-illegal chars
    return base[:120] or "Paper"


def _safe_paper_name(raw: str) -> str:
    """A _safe_name for the STUDENT PAPER filename specifically. The download
    matcher (console isPaper) treats any file whose name contains "answer key" /
    "solution" / "complete" as NOT the student paper, so a paper named e.g.
    "Solution Practice" would be un-downloadable as the paper. Strip those reserved
    matcher words (the console does this client-side; do it on the backend too so a
    direct API call or an upload-derived name is always matcher-safe). The separate
    key/solution files get their suffixes added AFTER this, so they still match."""
    import re
    base = _safe_name(raw)
    base = re.sub(r"(?i)\b(answer\s*key|solution|complete)\b", "", base)
    base = re.sub(r"\s{2,}", " ", base).strip(" -")
    return base[:120] or "Paper"


def _safe_output_path(job_id: str, filename: str) -> Path:
    """Build an output path and PROVE it stays inside the job's output dir.

    Defense-in-depth on top of _safe_name: even if a filename slips through with a
    traversal sequence, resolve it and confirm the job output dir is a parent —
    the same containment check _save_upload uses for uploads. Raises on escape."""
    out_dir = jobs.output_dir(job_id).resolve()
    dest = (out_dir / filename).resolve()
    if out_dir != dest and out_dir not in dest.parents:
        raise ValueError(f"unsafe output path escapes job dir: {filename!r}")
    return dest


def _wrap_questions(questions: list[dict], meta: dict) -> dict:
    """Build the universal top-level JSON the pipeline/builders consume."""
    # _safe_paper_name strips reserved matcher words ("answer key"/"solution"/
    # "complete") from the BASE name so the student paper filename ("<name>.docx")
    # stays downloadable; the key/solution filenames re-add their own suffixes
    # below, so those still match as answer-key/solution.
    name = _safe_paper_name(meta.get("paper_name", "Paper"))
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
    """When a question has no answer in the source, DON'T fake one. Leave the
    answer empty and flag it — the builders render a blank "—" with a clear
    "answer key not provided" note instead of a misleading all-(a) key."""
    for q in data["questions"]:
        if not q.get("answer"):
            q["answer"] = ""          # blank, not a fake "a"
            q["flag"] = "उत्तर कुंजी उपलब्ध नहीं"


def _run_builders(job_id: str, data: dict, font: str) -> tuple[list[dict], int]:
    """Write the questions JSON into the job's input dir, run run_pipeline.run()
    pointed at the job's output dir, return (output manifest, built_count).

    built_count is the number of questions ACTUALLY in the built paper — i.e. after
    run_pipeline.validate() drops any malformed ones and writes the cleaned JSON
    back to qjson. This is what the UI should report; the pre-validation extracted
    count can be higher and misleads the user about what's in the PDF."""
    import run_pipeline

    qjson = jobs.input_dir(job_id) / "questions.json"
    qjson.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Point the pipeline's output at THIS job's folder (it defaults to the
    # client's review/output). Pass it EXPLICITLY — mutating the module-global
    # run_pipeline.OUTPUT_DIR was a latent cross-job leak (two jobs in one process
    # would clobber each other's output dir if the pool were ever non-prefork).
    run_pipeline.run(qjson, font=font, output_dir=jobs.output_dir(job_id))

    # validate() rewrote qjson with only the questions that made it into the paper.
    try:
        built = json.loads(qjson.read_text(encoding="utf-8"))
        built_count = len(built.get("questions", []))
    except Exception:
        built_count = len(data.get("questions", []))
    return jobs.list_outputs(job_id), built_count


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
        outputs, built = _run_builders(job_id, data, font)
        jobs.update_meta(job_id, status="DONE", outputs=outputs, n_questions=built)
        return {"status": "DONE", "outputs": outputs, "n_questions": built}
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
        # SECURITY: paper_name is attacker-controlled; it MUST go through _safe_name
        # before being spliced into an output path, or "../../.." escapes the job
        # dir (arbitrary file write). _wrap_questions already sanitizes the name it
        # embeds, but this output path was using the raw value — sanitize here too.
        name = _safe_name(meta.get("paper_name", "Paper"))
        out = _safe_output_path(job_id, f"{name} - Answer Key.pdf")
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

        # SECURITY: sanitize paper_name before it reaches the output path (see
        # answer_key_task) — the raw value allows path traversal / arbitrary write.
        name = _safe_name(meta.get("paper_name", "Paper"))
        out = _safe_output_path(job_id, f"{name} - Solution (Teacher).docx")
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
    # Track REAL API spend for this run (Mayank wants actuals, not estimates).
    # reset here; every LLM call self-records; we read + log the total at the end.
    import llm
    llm.reset_usage()
    try:
        src = next(jobs.input_dir(job_id).iterdir())
        extracted = _extract_any(src)
        jobs.update_meta(job_id, stage="review",
                         n_questions=len(extracted.get("questions", [])))

        data = _wrap_questions(extracted["questions"], meta)
        # light OCR proofread (only obvious typos; proper nouns/facts untouched)
        try:
            import proofread
            proofread.proofread(data)
        except Exception as e:
            print(f"[full_task] proofread skipped ({type(e).__name__}: {e})", flush=True)
        # mark the correct option + solution from the institute DB, when confident;
        # leave blank otherwise (never guess)
        try:
            import answer_from_rag
            answer_from_rag.mark_answers(data)
        except Exception as e:
            print(f"[full_task] answer-marking skipped ({type(e).__name__}: {e})", flush=True)
        jobs.update_meta(job_id, stage="build")
        _placeholder_answers(data)
        outputs, built = _run_builders(job_id, data, font)
        # Report the count ACTUALLY in the paper (post-validate), not the
        # pre-validation extracted count. If a large fraction was dropped, flag it
        # so a silently-short paper is visible rather than shipping as a clean DONE.
        extracted_n = len(extracted.get("questions", []))
        note = None
        if extracted_n and built < extracted_n * 0.9:
            note = (f"{extracted_n - built} of {extracted_n} extracted question(s) "
                    f"were dropped as unusable; the paper has {built}.")
            print(f"[full_task] {note}", flush=True)
        # Real spend for this run: log it and attach to the job meta so the console
        # can surface it. This is ACTUAL usage from each API response, not an estimate.
        usage = llm.usage_summary()
        print(f"[full_task] SPEND job={job_id} total=${usage['total_usd']} "
              f"(llm ${usage['llm_usd']} + sarvam ${usage['sarvam_usd']}) "
              f"tokens in/out={usage['input_tokens']}/{usage['output_tokens']} "
              f"calls={usage['n_llm_calls']} sarvam_pages={usage['sarvam_pages']}",
              flush=True)
        jobs.update_meta(job_id, status="DONE", outputs=outputs,
                         n_questions=built, extracted_questions=extracted_n,
                         note=note, usage=usage)
        return {"status": "DONE", "outputs": outputs, "n_questions": built,
                "usage": usage}
    except Exception as e:
        jobs.update_meta(job_id, status="FAILED", error=f"{type(e).__name__}: {e}")
        raise


@shared_task(bind=True, name="worker.tasks.generate")
def generate_task(self, job_id: str, subject: str, count: int, meta: dict):
    """AI Generative: subject + count -> generate N questions from the book corpus
    (RAG + LLM, see worker.generate) -> run the existing build pipeline -> same
    deliverables as /api/full. No upload involved."""
    import asyncio
    from . import generate

    font = (meta.get("font") or "krutidev").lower()
    jobs.update_meta(job_id, status="RUNNING", stage="generate", font=font,
                     format=meta.get("format", "format-1"))
    try:
        # phases 1-3: produce the questions list (async pipeline, run to completion)
        questions = asyncio.run(generate.generate_questions(subject, count))
        if not questions:
            raise RuntimeError("Generation produced no questions.")

        jobs.update_meta(job_id, stage="build", n_questions=len(questions))

        # phase 4: identical to the build path the other tools use
        data = _wrap_questions(questions, meta)
        _placeholder_answers(data)
        outputs, built = _run_builders(job_id, data, font)
        jobs.update_meta(job_id, status="DONE", outputs=outputs, n_questions=built)
        return {"status": "DONE", "outputs": outputs, "n_questions": built}
    except Exception as e:
        jobs.update_meta(job_id, status="FAILED", error=f"{type(e).__name__}: {e}")
        raise


@shared_task(name="worker.tasks.cleanup_jobs")
def cleanup_jobs():
    """Beat task: purge job folders past their TTL."""
    return jobs.cleanup_expired(settings.JOB_TTL_HOURS)


# A RUNNING job whose meta.json hasn't been touched in this long is dead — past
# the 20-min hard time limit plus a safety buffer, so we never reap a job that is
# merely slow. A live job rewrites meta on each stage transition.
_STUCK_JOB_SECONDS = 25 * 60


@shared_task(name="worker.tasks.reap_stuck_jobs")
def reap_stuck_jobs():
    """Beat task: flip jobs stuck in RUNNING past the hard time limit to FAILED so
    the UI stops spinning forever on a crashed/killed worker."""
    n = jobs.reap_stuck(_STUCK_JOB_SECONDS)
    if n:
        print(f"[reap_stuck_jobs] marked {n} stuck job(s) FAILED", flush=True)
    return n
