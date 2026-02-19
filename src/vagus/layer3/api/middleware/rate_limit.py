"""
Rate limiter middleware with role-based limits and optional Redis backend.
"""

from __future__ import annotations

import secrets
import time
from collections import defaultdict
from collections import deque
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from vagus.layer0.logging import get_logger

from ..auth import decode_access_token

logger = get_logger("layer3.api.rate_limit")


class _InMemoryRateLimiter:
    """Sliding-window limiter in process memory."""

    def __init__(self):
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def is_allowed(self, *, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        window_start = now - window_seconds
        queue = self._requests[key]
        while queue and queue[0] <= window_start:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True


class _RedisRateLimiter:
    """Sliding-window limiter backed by Redis sorted sets."""

    def __init__(self, redis_url: str):
        try:
            import redis.asyncio as redis  # type: ignore[import-untyped]
        except Exception as exc:  # pragma: no cover - import-guard
            raise RuntimeError("redis package is not available") from exc
        self._redis = redis.from_url(redis_url, decode_responses=True)

    async def is_allowed(self, *, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"rate_limit:{key}"

        await self._redis.zremrangebyscore(redis_key, "-inf", window_start)
        current_count = await self._redis.zcard(redis_key)
        if int(current_count) >= limit:
            return False

        member = f"{now}:{secrets.token_hex(4)}"
        await self._redis.zadd(redis_key, {member: now})
        await self._redis.expire(redis_key, int(window_seconds) + 1)
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Ограничение частоты запросов.

    Поддерживает:
    - legacy режим с max_requests/window_seconds
    - role-based режим (anonymous/user/admin)
    - Redis backend при наличии redis_url
    """

    def __init__(
        self,
        app,
        max_requests: Optional[int] = None,
        window_seconds: int = 60,
        anonymous_requests_per_minute: int = 10,
        user_requests_per_minute: int = 100,
        admin_requests_per_minute: int = 1000,
        redis_url: Optional[str] = None,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.anonymous_requests_per_minute = anonymous_requests_per_minute
        self.user_requests_per_minute = user_requests_per_minute
        self.admin_requests_per_minute = admin_requests_per_minute
        self._fixed_mode = max_requests is not None

        self._memory_backend = _InMemoryRateLimiter()
        self._redis_backend: Optional[_RedisRateLimiter] = None
        if redis_url:
            try:
                self._redis_backend = _RedisRateLimiter(redis_url)
                logger.info("RateLimitMiddleware uses Redis backend: %s", redis_url)
            except Exception as exc:
                logger.warning("RateLimitMiddleware Redis unavailable, fallback to memory: %s", exc)
                self._redis_backend = None

    @staticmethod
    def _extract_role_and_key(request: Request) -> tuple[str, str]:
        client_ip = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return "anonymous", f"anon:{client_ip}"

        token = auth_header.split(" ", 1)[1].strip()
        payload = decode_access_token(token)
        if payload is None:
            return "anonymous", f"anon:{client_ip}"

        user_id = payload.get("sub", "unknown")
        role = payload.get("role", "user")
        if role == "admin":
            return "admin", f"admin:{user_id}"
        return "user", f"user:{user_id}"

    def _limit_for_role(self, role: str) -> int:
        if role == "admin":
            return self.admin_requests_per_minute
        if role == "user":
            return self.user_requests_per_minute
        return self.anonymous_requests_per_minute

    async def _is_allowed(self, *, key: str, limit: int) -> bool:
        if self._redis_backend is not None:
            try:
                return await self._redis_backend.is_allowed(
                    key=key,
                    limit=limit,
                    window_seconds=self.window_seconds,
                )
            except Exception as exc:
                logger.warning("Redis rate limit backend failed; fallback to memory: %s", exc)
                self._redis_backend = None

        return await self._memory_backend.is_allowed(
            key=key,
            limit=limit,
            window_seconds=self.window_seconds,
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._fixed_mode:
            client_ip = request.client.host if request.client else "unknown"
            key = f"ip:{client_ip}"
            limit = int(self.max_requests or 0)
        else:
            role, key = self._extract_role_and_key(request)
            limit = self._limit_for_role(role)

        if not await self._is_allowed(key=key, limit=limit):
            return JSONResponse(
                content={"detail": "Rate limit exceeded"},
                status_code=429,
            )
        return await call_next(request)
