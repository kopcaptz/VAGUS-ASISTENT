"""
In-memory rate limiter middleware.
"""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Ограничение частоты запросов по IP.
    В production рекомендуется Redis-backed решение.
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self.window_seconds

        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > window_start
        ]

        if len(self._requests[client_ip]) >= self.max_requests:
            return JSONResponse(
                content={"detail": "Rate limit exceeded"},
                status_code=429,
            )

        self._requests[client_ip].append(now)
        return await call_next(request)
