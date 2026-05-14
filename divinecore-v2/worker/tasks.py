import asyncio
from datetime import datetime
from celery_app import app
from branding_os.agents.imagyn import run as imagyn_run
from branding_os.agents.lyra import run as lyra_run


@app.task(name="tasks.echo")
def echo(message: str) -> str:
    result = message.upper()
    print(f"[echo] {message} -> {result}", flush=True)
    return result


@app.task(name="tasks.heartbeat")
def heartbeat() -> str:
    now = datetime.utcnow().isoformat()
    print(f"[heartbeat] {now}", flush=True)
    return now


@app.task(name="tasks.imagyn_run")
def imagyn_task(username: str, message: str, channel_id: str, message_id: str) -> str:
    return asyncio.get_event_loop().run_until_complete(
        imagyn_run(username, message, channel_id, message_id)
    )


@app.task(name="tasks.lyra_run")
def lyra_task(username: str, message: str, channel_id: str, message_id: str) -> str:
    return asyncio.get_event_loop().run_until_complete(
        lyra_run(username, message, channel_id, message_id)
    )
