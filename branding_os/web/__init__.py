"""HTTP-facing layer for Branding OS — FastAPI routers + Jinja templates.

Routers exported here are mounted by `divinecore-v2/api/main.py`.
"""

from .imagyn_routes import imagyn_router
from .lyra_routes import lyra_router
from .social_perf_routes import router as social_perf_router

__all__ = ["imagyn_router", "lyra_router", "social_perf_router"]
