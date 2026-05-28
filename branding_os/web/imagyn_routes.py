from fastapi import APIRouter
from pydantic import BaseModel
from celery import Celery
import os

imagyn_router = APIRouter()
celery_client = Celery("api", broker=os.getenv("REDIS_URL"), backend=os.getenv("REDIS_URL"))


class DiscordPayload(BaseModel):
    username: str
    message: str
    author_id: str
    channel_id: str
    message_id: str


@imagyn_router.post("/imagyn")
def imagyn(payload: DiscordPayload):
    task = celery_client.send_task(
        "tasks.imagyn_run",
        args=[payload.username, payload.message, payload.channel_id, payload.message_id]
    )
    return {"status": "queued", "task_id": task.id}
