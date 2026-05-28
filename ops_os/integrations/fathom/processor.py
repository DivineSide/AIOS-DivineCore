from celery_app import app

from . import categorizer, supabase_writer, tasks_writer


@app.task(name="tasks.process_fathom_recording")
def process_fathom_recording(payload: dict) -> dict:
    category = categorizer.classify(payload)
    meeting_record = supabase_writer.upsert(payload, category)

    try:
        tasks = tasks_writer.create_tasks_for_opted_in(payload, meeting_record)
    except Exception as exc:
        print(f"[fathom] tasks_writer failed (non-fatal): {exc}", flush=True)
        tasks = []

    return {
        "meeting_id": payload.get("recording_id"),
        "category": category,
        "supabase_meeting_id": (meeting_record or {}).get("meeting_id"),
        "tasks_created": len(tasks),
    }
