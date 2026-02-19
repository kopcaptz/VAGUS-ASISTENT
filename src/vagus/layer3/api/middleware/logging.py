"""
Request logging middleware.
Logs every incoming request with method, path, status code and duration.
"""

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from vagus.layer0.logging import get_logger

logger = get_logger("layer3.middleware")


class RequestLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = str(uuid.uuid4())[:8]
        request.state.trace_id = trace_id

        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        logger.info(
            "[%s] %s %s -> %d (%.1fms)",
            trace_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        response.headers["X-Trace-Id"] = trace_id
        return response
