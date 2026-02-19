"""
IP whitelist middleware for admin endpoints.
"""

from __future__ import annotations

import ipaddress
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from vagus.layer0.logging import get_logger

logger = get_logger("layer3.api.ip_whitelist")


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """
    Restricts /api/v1/admin/* endpoints to configured IP/CIDR ranges.
    """

    def __init__(
        self,
        app,
        *,
        admin_path_prefix: str = "/api/v1/admin/",
        whitelist: Iterable[str] | None = None,
    ):
        super().__init__(app)
        self.admin_path_prefix = admin_path_prefix
        self.whitelist = [item.strip() for item in (whitelist or []) if item and item.strip()]
        self._networks = self._parse_networks(self.whitelist)

    @staticmethod
    def _parse_networks(raw_items: list[str]) -> list[ipaddress._BaseNetwork]:
        networks: list[ipaddress._BaseNetwork] = []
        for raw in raw_items:
            try:
                if "/" in raw:
                    networks.append(ipaddress.ip_network(raw, strict=False))
                else:
                    networks.append(ipaddress.ip_network(f"{raw}/32", strict=False))
            except ValueError:
                logger.warning("Invalid IP whitelist entry ignored: %s", raw)
        return networks

    def _is_allowed(self, client_ip: str) -> bool:
        if not self._networks:
            return True
        try:
            ip_obj = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        return any(ip_obj in network for network in self._networks)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith(self.admin_path_prefix):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if self._is_allowed(client_ip):
            return await call_next(request)

        logger.warning(
            "Admin endpoint access denied by IP whitelist: ip=%s path=%s",
            client_ip,
            path,
        )
        return JSONResponse(
            status_code=403,
            content={"detail": "Forbidden: IP not allowed"},
        )
