"""Tests for telegram plugin integration registry."""

from __future__ import annotations

import pytest

from vagus.plugins.integration import TelegramPluginIntegration


@pytest.mark.asyncio
async def test_telegram_integration_process_message():
    integration = TelegramPluginIntegration()

    async def handler(message_text: str, context: dict) -> str | None:
        if message_text == "ping":
            return f"pong:{context['user_id']}"
        return None

    integration.register_message_handler("demo", handler)
    result = await integration.process_message("ping", {"user_id": "u1"})
    assert result == "pong:u1"


@pytest.mark.asyncio
async def test_telegram_integration_inline_button_callbacks():
    integration = TelegramPluginIntegration()

    async def button_handler(context: dict) -> str:
        return f"clicked:{context['chat_id']}"

    integration.register_inline_button(
        plugin_name="demo",
        text="Demo",
        callback_data="demo_click",
        handler=button_handler,
    )
    result = await integration.process_callback("demo_click", {"chat_id": "c1"})
    assert result == "clicked:c1"


def test_telegram_integration_discovers_plugin_extensions():
    integration = TelegramPluginIntegration()

    class PluginRuntime:
        async def handle_telegram_message(self, message_text: str, context: dict) -> str | None:
            if message_text.startswith("/demo"):
                return "demo-response"
            return None

        def get_telegram_buttons(self):
            async def handler(context: dict) -> str:
                return "demo-button-response"

            return [{"text": "Demo", "callback_data": "demo", "handler": handler}]

    integration.discover_from_plugin("demo", PluginRuntime())
    buttons = integration.get_inline_buttons()
    assert len(buttons) == 1
    assert buttons[0]["callback_data"] == "demo"


@pytest.mark.asyncio
async def test_telegram_integration_returns_none_when_not_handled():
    integration = TelegramPluginIntegration()

    async def handler(_: str, __: dict) -> None:
        return None

    integration.register_message_handler("demo", handler)
    result = await integration.process_message("unknown", {"user_id": "u1"})
    assert result is None
