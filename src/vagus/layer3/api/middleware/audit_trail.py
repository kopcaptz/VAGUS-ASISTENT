"""
HTTP audit middleware: logs API and CLI actions into audit_log.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from vagus.layer0.logging import get_logger

from ..auth import decode_access_token
from ..audit.audit_trail import AuditTrail

logger = get_logger("layer3.api.audit_middleware")


class AuditTrailMiddleware(BaseHTTPMiddleware):
    """Records request-level audit entries for HTTP endpoints."""

    def __init__(self, app, *, max_body_bytes: int = 4096):
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    @staticmethod
    def _extract_user_id(request: Request) -> Optional[str]:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return None
        token = auth_header.split(" ", 1)[1].strip()
        payload = decode_access_token(token)
        if payload is None:
            return None
        return payload.get("sub")

    async def _safe_request_body(self, request: Request) -> bytes:
        try:
            body = await request.body()
        except Exception:
            return b""
        if len(body) <= self.max_body_bytes:
            return body
        return body[: self.max_body_bytes]

    @staticmethod
    def _parse_json_or_text(payload: bytes) -> Any:
        if not payload:
            return {}
        try:
            text = payload.decode("utf-8", errors="ignore")
            if not text:
                return {}
            return json.loads(text)
        except Exception:
            return payload.decode("utf-8", errors="ignore")

    def _get_storage(self, request: Request) -> Optional[AuditTrail]:
        storage = getattr(request.app.state, "audit_trail", None)
        if isinstance(storage, AuditTrail):
            return storage
        return None

    async def dispatch(self, request: Request, call_next) -> Response:
        storage = self._get_storage(request)
        if storage is None:
            return await call_next(request)

        started = time.monotonic()
        body = await self._safe_request_body(request)
        user_id = self._extract_user_id(request)
        client_ip = request.client.host if request.client else None

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            status_code = 500
            self._write_audit(
                storage=storage,
                request=request,
                user_id=user_id,
                client_ip=client_ip,
                status_code=status_code,
                duration_ms=(time.monotonic() - started) * 1000,
                body=body,
                error=str(exc),
            )
            raise

        self._write_audit(
            storage=storage,
            request=request,
            user_id=user_id,
            client_ip=client_ip,
            status_code=status_code,
            duration_ms=(time.monotonic() - started) * 1000,
            body=body,
            error=None,
        )
        return response

    def _write_audit(
        self,
        *,
        storage: AuditTrail,
        request: Request,
        user_id: Optional[str],
        client_ip: Optional[str],
        status_code: int,
        duration_ms: float,
        body: bytes,
        error: Optional[str],
    ) -> None:
        cli_command = request.headers.get("x-vagus-cli-command")
        cli_args = request.headers.get("x-vagus-cli-arguments")
        if cli_command:
            action = "cli.command"
            resource = cli_command
        else:
            action = "api.request"
            resource = f"{request.method.upper()} {request.url.path}"

        details: dict[str, Any] = {
            "path": request.url.path,
            "method": request.method.upper(),
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "query": dict(request.query_params),
            "parameters": self._parse_json_or_text(body),
        }
        if cli_args:
            details["arguments"] = cli_args
        if error:
            details["error"] = error

        try:
            storage.log_action(
                user_id=user_id,
                action=action,
                resource=resource,
                details=details,
                ip_address=client_ip,
            )
        except Exception as exc:
            logger.warning("Failed to write audit log entry: %s", exc)
