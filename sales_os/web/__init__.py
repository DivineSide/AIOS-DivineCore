"""HTTP-facing layer for Sales OS — FastAPI routers + Jinja templates.

Routers exported here are mounted by `divinecore-v2/api/main.py`.
"""

from .instantly_routes import router as instantly_router
from .upwork_jobs_routes import router as upwork_jobs_router
from .upwork_routes import router as upwork_router

__all__ = ["instantly_router", "upwork_jobs_router", "upwork_router"]
