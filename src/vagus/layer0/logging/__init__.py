"""
Модуль логирования для Vagus Asistent.
Единообразная настройка логгеров для всех компонентов.
"""

import logging
import sys
from typing import Optional

# Глобальный флаг: была ли выполнена базовая настройка
_configured = False


def get_logger(name: str) -> logging.Logger:
    """
    Возвращает настроенный логгер.
    
    Args:
        name: Имя логгера (например, "cache", "circuit_breaker")
        
    Returns:
        Настроенный экземпляр logging.Logger
    """
    global _configured
    if not _configured:
        _configure_root()
        _configured = True
    
    # Все логгеры под vagus.* для наследования настроек
    logger_name = name if name.startswith("vagus.") else f"vagus.{name}"
    return logging.getLogger(logger_name)


def _configure_root() -> None:
    """Базовая настройка корневого логгера."""
    root = logging.getLogger("vagus")
    if root.handlers:
        return
    
    handler = logging.StreamHandler(sys.stdout)
    if hasattr(handler.stream, "reconfigure"):
        try:
            handler.stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def set_log_level(level: int) -> None:
    """Устанавливает глобальный уровень логирования."""
    logging.getLogger("vagus").setLevel(level)


def configure_from_config(config: Optional[object]) -> None:
    """
    Настраивает логирование из конфигурации (если доступен ConfigManager).
    
    Args:
        config: AppConfig или объект с атрибутом global_settings.log_level
    """
    if config is None:
        return
    try:
        log_level_name = getattr(config, "global_settings", None)
        if log_level_name:
            level = getattr(log_level_name, "log_level", "INFO")
            level_str = str(level).upper() if hasattr(level, "upper") else str(level)
            level_map = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
                "CRITICAL": logging.CRITICAL,
            }
            logging.getLogger("vagus").setLevel(level_map.get(level_str, logging.INFO))
    except Exception:
        pass


__all__ = ["get_logger", "set_log_level", "configure_from_config"]
