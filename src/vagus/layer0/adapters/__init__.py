"""
Configuration adapter module.

Provides a safe, zero-import-cost way for any layer to read configuration
values.  When a ConfigManager instance has been initialised (e.g. by the
API gateway or CLI entry-point), values are read from the loaded YAML +
environment overlay.  When no ConfigManager is available (unit-tests,
lightweight scripts), the adapter falls back to ``os.getenv()`` so that
the rest of the codebase never crashes on missing config.

Usage::

    from vagus.layer0.adapters import config_adapter

    secret = config_adapter.get("layer3.auth.secret_key",
                                env_fallback="VAGUS_SECRET_KEY",
                                default="dev-secret")

    ttl = config_adapter.get_int("layer1.cache.ttl_seconds",
                                  env_fallback="VAGUS_CACHE_TTL",
                                  default=3600)
"""

import os
from typing import Any, Optional

from ..config.config_manager import ConfigManager

_instance: Optional[ConfigManager] = None


def bind(cm: ConfigManager) -> None:
    """
    Binds a ConfigManager instance to the adapter.
    Called once during application startup.
    """
    global _instance
    _instance = cm


def get_manager() -> Optional[ConfigManager]:
    """Returns the bound ConfigManager (or None)."""
    return _instance


def get(
    dotted_path: str,
    *,
    env_fallback: Optional[str] = None,
    default: Any = None,
) -> Any:
    """
    Reads a configuration value.

    Resolution order:
      1. Environment variable ``env_fallback`` (if provided and set)
      2. ConfigManager dotted path (if bound)
      3. ``default``

    Args:
        dotted_path: Dot-separated config path (e.g. "layer1.cache.ttl_seconds")
        env_fallback: Name of an environment variable to check first
        default: Returned when neither env nor config has the value
    """
    if env_fallback:
        env_val = os.getenv(env_fallback)
        if env_val is not None:
            return env_val

    if _instance is not None:
        try:
            val = _instance.get(dotted_path, default=_MISSING)
            if val is not _MISSING:
                return val
        except Exception:
            pass

    return default


def get_int(
    dotted_path: str,
    *,
    env_fallback: Optional[str] = None,
    default: int = 0,
) -> int:
    """Same as ``get()`` but coerces the result to ``int``."""
    val = get(dotted_path, env_fallback=env_fallback, default=default)
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def get_float(
    dotted_path: str,
    *,
    env_fallback: Optional[str] = None,
    default: float = 0.0,
) -> float:
    """Same as ``get()`` but coerces the result to ``float``."""
    val = get(dotted_path, env_fallback=env_fallback, default=default)
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def get_bool(
    dotted_path: str,
    *,
    env_fallback: Optional[str] = None,
    default: bool = False,
) -> bool:
    """Same as ``get()`` but coerces the result to ``bool``."""
    val = get(dotted_path, env_fallback=env_fallback, default=default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


_MISSING = object()

# Convenience alias
config_adapter = type("_ConfigAdapterProxy", (), {
    "bind": staticmethod(bind),
    "get_manager": staticmethod(get_manager),
    "get": staticmethod(get),
    "get_int": staticmethod(get_int),
    "get_float": staticmethod(get_float),
    "get_bool": staticmethod(get_bool),
})()

__all__ = [
    "bind",
    "get_manager",
    "get",
    "get_int",
    "get_float",
    "get_bool",
    "config_adapter",
]
