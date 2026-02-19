"""
Telegram bot entrypoint using aiogram 3.x.
"""

import logging
import os

from aiogram import Bot, Dispatcher

from ..gateway import ChannelGateway
from .handlers import router, set_gateway
from .middleware import UserAuthMiddleware


async def start_telegram_bot(
    token: str | None = None,
    api_url: str = "http://localhost:8000",
    api_key: str = "",
):
    """
    Starts the Telegram bot with long-polling.

    Args:
        token: Telegram bot token (defaults to TELEGRAM_BOT_TOKEN env var)
        api_url: Vagus REST API base URL
        api_key: JWT token for API authentication
    """
    token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    gateway = ChannelGateway(api_url=api_url, api_key=api_key)
    set_gateway(gateway)

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.message.middleware(UserAuthMiddleware())
    dp.include_router(router)

    logging.info("Starting Telegram bot...")
    await dp.start_polling(bot)
