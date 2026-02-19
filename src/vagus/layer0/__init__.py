"""
Слой 0: Конфигурация, логирование, адаптеры.
"""
from .config import ConfigManager, AppConfig
from .logging import get_logger

__all__ = ["ConfigManager", "AppConfig", "get_logger"]
