"""
Telegram бот на aiogram 3.x.
Точка входа и настройка Bot, Dispatcher, роутеров.
"""

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from ..gateway import ChannelGateway
from .handlers import register_handlers, router
from .middleware import UserAuthMiddleware


def start_telegram_bot(
    token: str,
    api_url: str,
    api_key: str,
) -> None:
    """
    Запускает Telegram бота.
    token: токен бота (или из TELEGRAM_BOT_TOKEN)
    api_url: URL Vagus API
    api_key: JWT access token для API
    """
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан")

    bot = Bot(token=bot_token, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    gateway = ChannelGateway(api_url=api_url, api_key=api_key, timeout=120)

    router.message.middleware(UserAuthMiddleware())
    register_handlers(gateway)
    dp.include_router(router)

    async def main() -> None:
        await dp.start_polling(bot)

    asyncio.run(main())
