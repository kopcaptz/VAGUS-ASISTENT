"""
Интеграция горячей перезагрузки конфигурации.
"""

from typing import Callable, Any, Optional
from ...layer0.logging import get_logger


class HotReloadIntegration:
    """Подписка на ConfigManager для перезагрузки стратегий и провайдеров."""

    def __init__(self, config_manager: Any, router: Any):
        """
        Args:
            config_manager: ConfigManager с register_callback
            router: LLMRouter для обновления
        """
        self.config_manager = config_manager
        self.router = router
        self.logger = get_logger("integration.hot_reload")

    def register(self) -> None:
        """Регистрирует колбэк перезагрузки."""
        if not hasattr(self.config_manager, "register_callback"):
            self.logger.warning("ConfigManager has no register_callback")
            return

        def on_config_changed(new_config: Any) -> None:
            self.logger.info("Config changed, hot-reload triggered")
            try:
                if hasattr(self.router, "_initialized") and self.router._initialized:
                    layer1 = getattr(new_config, "layer1", None) or {}
                    if isinstance(layer1, dict):
                        providers_cfg = layer1.get("providers", {})
                    else:
                        providers_cfg = getattr(layer1, "providers", {}) or {}
                    if providers_cfg:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(self.router.initialize(providers_cfg))
                        else:
                            loop.run_until_complete(self.router.initialize(providers_cfg))
            except Exception as e:
                self.logger.error(f"Hot-reload failed: {e}")

        self.config_manager.register_callback(on_config_changed)
        self.logger.info("Hot-reload integration registered")
