"""API роутеры."""

from .tasks import router as tasks_router
from .agents import router as agents_router
from .status import router as status_router
from .auth import router as auth_router

__all__ = ["tasks_router", "agents_router", "status_router", "auth_router"]
