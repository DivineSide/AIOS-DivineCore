"""HTTP-facing layer for Sales OS — FastAPI routers + Jinja templates.

Routers exported here are mounted by `divinecore-v2/api/main.py`.
"""

from .crm_routes import router as crm_router
from .dialer_routes import router as dialer_router
from .instantly_routes import router as instantly_router
from .linkedin_routes import router as linkedin_router
from .upwork_jobs_routes import router as upwork_jobs_router
from .upwork_routes import router as upwork_router

__all__ = ["crm_router", "dialer_router", "instantly_router", "linkedin_router", "upwork_jobs_router", "upwork_router"]
