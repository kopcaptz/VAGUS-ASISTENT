"""
Telegram bot middleware for user authentication and rate limiting.
"""

import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message


class UserAuthMiddleware(BaseMiddleware):
    """
    Middleware that tracks user requests and enforces basic rate limiting.
    Allowed users can be restricted via allowed_user_ids (empty = allow all).
    """

    def __init__(
        self,
        allowed_user_ids: list[int] | None = None,
        rate_limit_seconds: float = 2.0,
    ):
        self.allowed_user_ids = set(allowed_user_ids) if allowed_user_ids else None
        self.rate_limit_seconds = rate_limit_seconds
        self._last_request: Dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0

        if self.allowed_user_ids and user_id not in self.allowed_user_ids:
            await event.answer("Access denied.")
            return

        now = time.monotonic()
        if now - self._last_request[user_id] < self.rate_limit_seconds:
            return  # silently drop rapid-fire messages
        self._last_request[user_id] = now

        return await handler(event, data)
