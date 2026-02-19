"""
Server-side verification for signed CLI requests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from vagus.layer0.logging import get_logger
from vagus.layer3.security.request_signing import (
    HEADER_CLIENT_ID,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    is_timestamp_fresh,
    load_client_secret,
    verify_request_signature,
)

logger = get_logger("layer3.api.request_signing")


class RequestSigningMiddleware(BaseHTTPMiddleware):
    """
    Validates HMAC signature headers produced by CLI clients.
    """

    def __init__(
        self,
        app,
        *,
        enabled: bool = False,
        credentials_path: Optional[str] = None,
        timestamp_ttl_seconds: int = 300,
        exempt_paths: Iterable[str] | None = None,
    ):
        super().__init__(app)
        self.enabled = enabled
        self.credentials_path = Path(credentials_path).expanduser() if credentials_path else None
        self.timestamp_ttl_seconds = timestamp_ttl_seconds
        self.exempt_paths = set(
            exempt_paths
            or {
                "/health",
                "/health/detailed",
                "/metrics",
                "/docs",
                "/redoc",
                "/openapi.json",
                "/api/v1/auth/token",
                "/api/v1/auth/refresh",
            }
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled:
            return await call_next(request)

        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in self.exempt_paths:
            return await call_next(request)

        client_id = request.headers.get(HEADER_CLIENT_ID, "").strip()
        timestamp = request.headers.get(HEADER_TIMESTAMP, "").strip()
        signature = request.headers.get(HEADER_SIGNATURE, "").strip()
        if not client_id or not timestamp or not signature:
            logger.warning("Signed request rejected: missing signature headers path=%s", path)
            return JSONResponse(status_code=401, content={"detail": "Missing request signature headers"})

        if not is_timestamp_fresh(timestamp, self.timestamp_ttl_seconds):
            logger.warning("Signed request rejected: stale timestamp client_id=%s path=%s", client_id, path)
            return JSONResponse(status_code=401, content={"detail": "Invalid request timestamp"})

        secret = load_client_secret(client_id, path=self.credentials_path)
        if not secret:
            logger.warning("Signed request rejected: unknown client_id=%s", client_id)
            return JSONResponse(status_code=401, content={"detail": "Unknown client credentials"})

        body = await request.body()
        signed_path = request.url.path
        if request.url.query:
            signed_path = f"{signed_path}?{request.url.query}"
        valid = verify_request_signature(
            signature=signature,
            secret=secret,
            method=request.method,
            path=signed_path,
            timestamp=timestamp,
            body=body,
            client_id=client_id,
        )
        if not valid:
            logger.warning("Signed request rejected: bad signature client_id=%s path=%s", client_id, path)
            return JSONResponse(status_code=401, content={"detail": "Invalid request signature"})

        request.state.client_id = client_id
        return await call_next(request)
