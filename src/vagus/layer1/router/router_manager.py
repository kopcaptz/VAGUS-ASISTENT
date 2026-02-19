"""
Менеджер роутера: состояние, hot-reload, статистика.
"""

from typing import Dict, Any, Optional, Callable
from .llm_router import LLMRouter
from ...layer0.logging import get_logger


class RouterManager:
    """Управление жизненным циклом LLMRouter."""

    def __init__(self, router: LLMRouter, config_manager=None):
        self.router = router
        self.config_manager = config_manager
        self.logger = get_logger("router.manager")

    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику роутера."""
        return self.router.get_stats()

    def register_config_callback(self, callback: Callable) -> None:
        """Регистрирует колбэк для hot-reload конфигурации."""
        if self.config_manager and hasattr(self.config_manager, "register_callback"):
            self.config_manager.register_callback(callback)
            self.logger.info("Config reload callback registered")
