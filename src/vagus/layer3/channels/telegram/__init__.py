"""
Telegram-канал для Vagus Asistent.
"""

from .bot import start_telegram_bot
from .handlers import router as telegram_router
from .middleware import UserAuthMiddleware

__all__ = [
    "start_telegram_bot",
    "telegram_router",
    "UserAuthMiddleware",
]
