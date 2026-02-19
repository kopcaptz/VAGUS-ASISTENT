"""Telegram integration registry for plugin-provided handlers and buttons."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


MessageHandler = Callable[[str, dict[str, Any]], Awaitable[Optional[str]]]
ButtonHandler = Callable[[dict[str, Any]], Awaitable[Optional[str]]]


@dataclass
class PluginInlineButton:
    plugin_name: str
    text: str
    callback_data: str
    handler: ButtonHandler


class TelegramPluginIntegration:
    """Stores plugin telegram handlers and dispatches messages/buttons."""

    def __init__(self) -> None:
        self._message_handlers: list[tuple[str, MessageHandler]] = []
        self._inline_buttons: list[PluginInlineButton] = []

    def register_message_handler(self, plugin_name: str, handler: MessageHandler) -> None:
        self._message_handlers.append((plugin_name, handler))

    def register_inline_button(
        self,
        *,
        plugin_name: str,
        text: str,
        callback_data: str,
        handler: ButtonHandler,
    ) -> None:
        self._inline_buttons.append(
            PluginInlineButton(
                plugin_name=plugin_name,
                text=text,
                callback_data=callback_data,
                handler=handler,
            )
        )

    async def process_message(self, message_text: str, context: dict[str, Any]) -> Optional[str]:
        for _, handler in self._message_handlers:
            result = await handler(message_text, context)
            if result is not None:
                return result
        return None

    async def process_callback(self, callback_data: str, context: dict[str, Any]) -> Optional[str]:
        for button in self._inline_buttons:
            if button.callback_data != callback_data:
                continue
            result = await button.handler(context)
            if result is not None:
                return result
        return None

    def get_inline_buttons(self) -> list[dict[str, str]]:
        return [
            {"plugin_name": item.plugin_name, "text": item.text, "callback_data": item.callback_data}
            for item in self._inline_buttons
        ]

    def discover_from_plugin(self, plugin_name: str, plugin_runtime: Any) -> None:
        target = self._resolve_runtime_target(plugin_runtime)
        message_handler = getattr(target, "handle_telegram_message", None)
        if callable(message_handler):
            self.register_message_handler(plugin_name, message_handler)

        buttons_provider = getattr(target, "get_telegram_buttons", None)
        if callable(buttons_provider):
            try:
                buttons = buttons_provider()
            except Exception:
                buttons = []
            if isinstance(buttons, list):
                for item in buttons:
                    if not isinstance(item, dict):
                        continue
                    text = str(item.get("text", "")).strip()
                    callback_data = str(item.get("callback_data", "")).strip()
                    handler = item.get("handler")
                    if text and callback_data and callable(handler):
                        self.register_inline_button(
                            plugin_name=plugin_name,
                            text=text,
                            callback_data=callback_data,
                            handler=handler,
                        )

    def clear(self) -> None:
        self._message_handlers.clear()
        self._inline_buttons.clear()

    @staticmethod
    def _resolve_runtime_target(plugin_runtime: Any) -> Any:
        if inspect.isclass(plugin_runtime):
            try:
                return plugin_runtime()
            except Exception:
                return plugin_runtime
        return plugin_runtime


_telegram_integration_singleton: Optional[TelegramPluginIntegration] = None


def get_telegram_plugin_integration() -> TelegramPluginIntegration:
    global _telegram_integration_singleton
    if _telegram_integration_singleton is None:
        _telegram_integration_singleton = TelegramPluginIntegration()
    return _telegram_integration_singleton
