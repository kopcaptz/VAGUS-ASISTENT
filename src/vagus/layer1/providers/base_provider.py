"""
Backward-compatible re-export for provider base primitives.
"""

from .base import (
    HTTPClientManager,
    HTTPClientPoolConfig,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)

__all__ = [
    "HTTPClientManager",
    "HTTPClientPoolConfig",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
]