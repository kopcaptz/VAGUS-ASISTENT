"""
Telegram Bot (aiogram 3.x) — точка входа.
"""

import os
from typing import Optional

try:
    from aiogram import Bot, Dispatcher

    AIOGRAM_AVAILABLE = True
except ImportError:
    AIOGRAM_AVAILABLE = False

from ..gateway import ChannelGateway
from .handlers import router as handlers_router, set_gateway
from ....plugins.integration import get_telegram_plugin_integration


async def start_telegram_bot(
    token: Optional[str] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    plugin_registry: Optional[object] = None,
):
    """
    Запуск Telegram-бота.

    Args:
        token: Токен бота (или TELEGRAM_BOT_TOKEN env)
        api_url: URL REST API (или VAGUS_API_URL env)
        api_key: API-ключ (или VAGUS_API_KEY env)
    """
    if not AIOGRAM_AVAILABLE:
        raise RuntimeError("aiogram not installed. pip install aiogram>=3.0")

    token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    api_url = api_url or os.getenv("VAGUS_API_URL", "http://localhost:8000")
    api_key = api_key or os.getenv("VAGUS_API_KEY", "")

    if not token:
        raise ValueError("Telegram bot token is required (TELEGRAM_BOT_TOKEN)")

    gw = ChannelGateway(api_url=api_url, api_key=api_key)
    set_gateway(gw)
    integration = get_telegram_plugin_integration()
    if plugin_registry is not None and hasattr(plugin_registry, "list_plugins"):
        for plugin in plugin_registry.list_plugins():
            runtime = plugin.entry_point
            if isinstance(runtime, type):
                try:
                    runtime = runtime()
                except Exception:
                    pass
            integration.discover_from_plugin(plugin.name, runtime)

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(handlers_router)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
