"""
Точка входа Telegram-бота Vagus Asistent.

Настройка Bot, Dispatcher, подключение handlers и middleware.
"""

import asyncio
import os
from typing import Set

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from ..gateway import ChannelGateway
from .handlers import router as telegram_router
from .middleware import UserAuthMiddleware
from ....layer0.logging import get_logger

logger = get_logger("layer3.telegram.bot")


def _parse_allowed_users(raw: str | None) -> Set[int]:
    """Парсит TELEGRAM_ALLOWED_USERS (через запятую) в set[int]."""
    if not raw:
        return set()
    result = set()
    for item in raw.split(","):
        item = item.strip()
        if item.isdigit():
            result.add(int(item))
    return result


async def start_telegram_bot(
    token: str,
    api_url: str,
    api_key: str,
    allowed_users: Set[int] | None = None,
) -> None:
    """
    Запускает Telegram-бота в режиме long-polling.

    Args:
        token: Токен Telegram-бота (TELEGRAM_BOT_TOKEN).
        api_url: URL API Vagus (например, http://localhost:8000).
        api_key: Ключ авторизации API.
        allowed_users: Множество разрешённых user_id (None = все).
    """
    gateway = ChannelGateway(api_url=api_url, api_key=api_key)

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.message.middleware(UserAuthMiddleware(allowed_users=allowed_users))

    dp.include_router(telegram_router)

    dp["gateway"] = gateway

    logger.info("Telegram bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Telegram bot stopped.")


def main() -> None:
    """
    Entry-point: загружает конфигурацию из переменных окружения и запускает бота.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Set it as an environment variable before starting the bot."
        )

    api_url = os.environ.get("VAGUS_API_URL", "http://localhost:8000")
    api_key = os.environ.get("VAGUS_API_KEY", "")
    allowed_users = _parse_allowed_users(
        os.environ.get("TELEGRAM_ALLOWED_USERS")
    )

    asyncio.run(
        start_telegram_bot(
            token=token,
            api_url=api_url,
            api_key=api_key,
            allowed_users=allowed_users or None,
        )
    )


if __name__ == "__main__":
    main()
