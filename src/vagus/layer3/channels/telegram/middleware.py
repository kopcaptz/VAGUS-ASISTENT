"""
Middleware для проверки пользователей Telegram.
"""

import os
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class UserAuthMiddleware(BaseMiddleware):
    """
    Middleware для проверки доступа пользователей.
    Если TELEGRAM_ALLOWED_USERS задан (через запятую), только эти user_id получают доступ.
    Если не задан — все пользователи допускаются.
    """

    def __init__(self) -> None:
        allowed = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        self.allowed_ids: set[int] = set()
        if allowed:
            for s in allowed.split(","):
                s = s.strip()
                if s.isdigit():
                    self.allowed_ids.add(int(s))

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif hasattr(event, "message") and event.message:
            user_id = event.message.from_user.id if event.message.from_user else None

        if user_id is not None and self.allowed_ids and user_id not in self.allowed_ids:
            if isinstance(event, Message):
                await event.answer("❌ Доступ запрещён. Ваш ID не в списке разрешённых.")
            return

        return await handler(event, data)
