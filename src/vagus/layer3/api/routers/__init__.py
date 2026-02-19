"""FastAPI роутеры."""

from .auth import router as auth_router
from .tasks import router as tasks_router
from .agents import router as agents_router
from .status import router as status_router
from .admin import router as admin_router

__all__ = ["auth_router", "tasks_router", "agents_router", "status_router", "admin_router"]
