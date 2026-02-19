"""
Обработчики команд и сообщений Telegram бота.
"""

from aiogram import Router, F
from aiogram.types import Message

from ..gateway import ChannelGateway

router = Router()


async def cmd_start(message: Message) -> None:
    """Обработчик /start."""
    await message.answer(
        "👋 Привет! Я Vagus Asistent.\n\n"
        "Отправь мне любой запрос, и я обработаю его через AI-агентов.\n\n"
        "Примеры:\n"
        "• Найди информацию о Python\n"
        "• Объясни квантовую запутанность"
    )


async def handle_text(message: Message, gateway: ChannelGateway) -> None:
    """Обработчик текстовых сообщений."""
    prompt = message.text or ""
    if not prompt.strip():
        await message.answer("Пожалуйста, введите текст запроса.")
        return

    status_msg = await message.answer("🤔 Обрабатываю запрос...")

    try:
        result = await gateway.process_message(
            user_id=str(message.from_user.id) if message.from_user else "unknown",
            chat_id=str(message.chat.id),
            prompt=prompt.strip(),
            task_type="default",
        )
        text = result[:4000] if len(result) > 4000 else result
        if len(result) > 4000:
            text += "\n\n... (обрезано)"
        await status_msg.edit_text(text)
    except TimeoutError as e:
        await status_msg.edit_text(f"⏱ Таймаут: {e}")
    except RuntimeError as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Непредвиденная ошибка: {e}")


def register_handlers(gateway: ChannelGateway) -> None:
    """Регистрирует обработчики с привязкой к gateway."""
    router.message.register(cmd_start, F.text == "/start")
    router.message.register(
        lambda msg: handle_text(msg, gateway),
        F.text & ~F.text.startswith("/"),
    )
