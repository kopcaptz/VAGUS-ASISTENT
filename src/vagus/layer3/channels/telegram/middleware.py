"""
Middleware для Telegram-бота.
"""

from typing import Any, Awaitable, Callable, Dict, Set

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from ....layer0.logging import get_logger

logger = get_logger("layer3.telegram.middleware")


class UserAuthMiddleware(BaseMiddleware):
    """
    Middleware для проверки доступа пользователей.

    Если allowed_users пуст — доступ открыт для всех.
    Если задан набор user_id — пропускает только их.
    """

    def __init__(self, allowed_users: Set[int] | None = None):
        self.allowed_users: Set[int] = allowed_users or set()
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not self.allowed_users:
            return await handler(event, data)

        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user

        if user is None:
            return await handler(event, data)

        if user.id not in self.allowed_users:
            logger.warning(
                f"Access denied for user_id={user.id} ({user.full_name})"
            )
            if isinstance(event, Message):
                await event.answer("🚫 Доступ запрещён. Обратитесь к администратору.")
            return None

        return await handler(event, data)
