"""
Модуль fallback: Circuit Breaker, Retry, Fallback Chain.
"""

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitBreakerState
from .retry_manager import RetryManager
from .retry_handler import RetryConfig, RetryHandler
from .fallback_chain import FallbackChain
from .fallback_handler import FallbackHandler

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "RetryManager",
    "RetryConfig",
    "RetryHandler",
    "FallbackChain",
    "FallbackHandler",
]
