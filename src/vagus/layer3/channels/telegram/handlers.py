"""
Обработчики команд и сообщений Telegram-бота.
"""

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from ..gateway import ChannelGateway
from ....layer0.logging import get_logger

logger = get_logger("layer3.telegram.handlers")

router = Router(name="telegram_handlers")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Приветственное сообщение по команде /start."""
    await message.answer(
        "👋 Привет! Я Vagus Asistent.\n\n"
        "Отправь мне текстовое сообщение, и я обработаю твой запрос.\n"
        "Поддерживаемые команды:\n"
        "  /start — это сообщение\n"
        "  /help — справка"
    )


@router.message(F.text == "/help")
async def cmd_help(message: Message) -> None:
    """Справочное сообщение."""
    await message.answer(
        "ℹ️ Vagus Asistent — интеллектуальная система обработки запросов.\n\n"
        "Просто напиши свой вопрос или задачу, и я передам его на обработку.\n"
        "Результат придёт в этот же чат."
    )


@router.message(F.text)
async def handle_text_message(message: Message, gateway: ChannelGateway) -> None:
    """
    Обработка произвольного текстового сообщения:
    1. Отправляем индикатор обработки
    2. Вызываем gateway.process_message()
    3. Редактируем сообщение с результатом
    """
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    prompt = message.text

    logger.info(f"Message from user={user_id} chat={chat_id}: {prompt[:80]}")

    thinking_msg = await message.answer("🤔 Обрабатываю запрос...")

    try:
        result = await gateway.process_message(
            user_id=user_id,
            chat_id=chat_id,
            prompt=prompt,
        )
        await thinking_msg.edit_text(result)
        logger.info(f"Response sent to user={user_id}")
    except TimeoutError:
        await thinking_msg.edit_text(
            "⏰ Превышено время ожидания. Попробуйте позже или упростите запрос."
        )
        logger.warning(f"Timeout for user={user_id}")
    except Exception as e:
        await thinking_msg.edit_text(
            "❌ Произошла ошибка при обработке запроса. Попробуйте позже."
        )
        logger.error(f"Error processing message for user={user_id}: {e}")
