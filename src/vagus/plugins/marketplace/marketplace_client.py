"""Marketplace integration primitives for plugins."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarketplaceClient:
    """Minimal marketplace URL builder and settings holder."""

    url: str = "https://plugins.vagus.ai"
    cache_ttl_hours: int = 24

    def plugin_details_url(self, plugin_name: str) -> str:
        """Build details URL for a plugin in marketplace API."""
        base = self.url.rstrip("/")
        return f"{base}/api/v1/plugins/{plugin_name}"
