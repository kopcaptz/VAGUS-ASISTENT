"""FastAPI роутеры."""

from .auth import router as auth_router
from .tasks import router as tasks_router
from .agents import router as agents_router
from .status import router as status_router
from .admin import router as admin_router
from .plugins import router as plugins_router
from .keys import router as keys_router
from .monitoring import router as monitoring_router
from .websocket_events import router as websocket_events_router

__all__ = [
    "auth_router",
    "tasks_router",
    "agents_router",
    "status_router",
    "admin_router",
    "plugins_router",
    "keys_router",
    "monitoring_router",
    "websocket_events_router",
]
