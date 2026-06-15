from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from celery import Celery

from branding_os.web import imagyn_router, lyra_router, social_perf_router
from sales_os.web import (
    crm_router,
    dialer_router,
    instantly_router,
    linkedin_router,
    upwork_jobs_router,
    upwork_router,
)
from settings import settings

celery_client = Celery("api", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

app = FastAPI(title="DivineCore v2")

# Serve the unified dashboard at /
_frontend = Path(__file__).parent.parent.parent / "frontend"
if _frontend.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend)), name="static")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (_frontend / "index.html").read_text()

app.include_router(upwork_router)
app.include_router(upwork_jobs_router)
app.include_router(instantly_router)
app.include_router(crm_router)
app.include_router(dialer_router)
app.include_router(linkedin_router)
app.include_router(imagyn_router)
app.include_router(lyra_router)
app.include_router(social_perf_router)


class EchoRequest(BaseModel):
    message: str


@app.get("/", response_class=HTMLResponse)
def root():
    return (_frontend / "index.html").read_text()


@app.post("/tasks/echo")
def trigger_echo(req: EchoRequest):
    result = celery_client.send_task("tasks.echo", args=[req.message])
    return {"task_id": result.id, "submitted": req.message}


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    result = celery_client.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }
