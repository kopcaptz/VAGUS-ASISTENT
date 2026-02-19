"""
Обработчики Telegram-сообщений.
"""

from typing import Optional

try:
    from aiogram import Router
    from aiogram.filters import Command, CommandStart
    from aiogram.types import Message

    AIOGRAM_AVAILABLE = True
except ImportError:
    AIOGRAM_AVAILABLE = False

from ..gateway import ChannelGateway

router = Router() if AIOGRAM_AVAILABLE else None  # type: ignore[assignment]
gateway: Optional[ChannelGateway] = None


def set_gateway(gw: ChannelGateway) -> None:
    global gateway
    gateway = gw


if AIOGRAM_AVAILABLE:

    @router.message(CommandStart())
    async def cmd_start(message: Message):
        await message.answer(
            "Привет! Я Vagus Asistent — ваш AI-помощник.\n\n"
            "Просто напишите мне запрос, и я выполню его с помощью AI-агентов.\n\n"
            "Команды:\n"
            "/status — статус системы\n"
            "/help — справка"
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        await message.answer(
            "Vagus Asistent — многослойная AI-система.\n\n"
            "Отправьте текстовый запрос, и система:\n"
            "1. Выберет подходящего агента\n"
            "2. Выполнит задачу через LLM\n"
            "3. Вернёт результат\n\n"
            "Поддерживаемые типы:\n"
            "- Исследование (research)\n"
            "- Программирование (code)\n"
            "- Анализ данных (analysis)"
        )

    @router.message(Command("status"))
    async def cmd_status(message: Message):
        if gateway is None:
            await message.answer("Gateway не настроен")
            return
        healthy = await gateway.health_check()
        status = "онлайн" if healthy else "недоступен"
        await message.answer(f"Статус API: {status}")

    @router.message()
    async def handle_message(message: Message):
        """Основной обработчик текстовых сообщений."""
        if gateway is None:
            await message.answer("Gateway не настроен. Обратитесь к администратору.")
            return

        if not message.text:
            return

        user_id = str(message.from_user.id) if message.from_user else "unknown"
        chat_id = str(message.chat.id)

        thinking_msg = await message.answer("Обрабатываю запрос...")

        try:
            result = await gateway.process_message(
                user_id=user_id,
                chat_id=chat_id,
                prompt=message.text,
            )
            text = result if len(result) <= 4096 else result[:4090] + "..."
            await thinking_msg.edit_text(text)
        except TimeoutError:
            await thinking_msg.edit_text("Таймаут: задача не завершилась вовремя.")
        except Exception as e:
            await thinking_msg.edit_text(f"Ошибка: {e}")
