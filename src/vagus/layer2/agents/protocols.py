"""Shared typing protocols for Layer2 agents dependencies."""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol


class LLMRouterProtocol(Protocol):
    """Minimal protocol required from LLM router."""

    def route_request(
        self,
        prompt: str,
        stream: bool = True,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream LLM response chunks."""
        ...


class PluginManagerProtocol(Protocol):
    """Minimal protocol required from plugin manager."""

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return installed plugins metadata."""
        ...

