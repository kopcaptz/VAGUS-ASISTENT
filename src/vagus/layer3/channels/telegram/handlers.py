"""
Telegram message handlers.
"""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..gateway import ChannelGateway

router = Router()

_gateway: ChannelGateway | None = None


def set_gateway(gw: ChannelGateway) -> None:
    """Sets the shared gateway instance."""
    global _gateway
    _gateway = gw


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Vagus Asistent — AI-powered assistant.\n\n"
        "Send me any text and I will process it with AI agents.\n\n"
        "Commands:\n"
        "/status — last task status\n"
        "/help — help"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Just type your request in natural language.\n"
        "Supported task types are chosen automatically:\n"
        "- research (information search)\n"
        "- code (code generation)\n"
        "- analysis (data analysis)\n"
    )


@router.message(Command("status"))
async def cmd_status(message: Message):
    if not _gateway:
        await message.answer("Bot is not connected to API.")
        return
    try:
        data = await _gateway.get_status()
        await message.answer(f"API status: {data.get('status', 'unknown')}")
    except Exception as e:
        await message.answer(f"Error checking status: {e}")


@router.message()
async def handle_message(message: Message):
    """Main handler for text messages — creates a task via the gateway."""
    if not message.text:
        return
    if not _gateway:
        await message.answer("Bot is not connected to API.")
        return

    user_id = str(message.from_user.id) if message.from_user else "unknown"
    chat_id = str(message.chat.id)

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    thinking_msg = await message.answer("Processing...")

    try:
        result = await _gateway.process_message(
            user_id=user_id,
            chat_id=chat_id,
            prompt=message.text,
        )
        # Telegram has a 4096 char limit per message
        if len(result) > 4000:
            for i in range(0, len(result), 4000):
                chunk = result[i : i + 4000]
                if i == 0:
                    await thinking_msg.edit_text(chunk)
                else:
                    await message.answer(chunk)
        else:
            await thinking_msg.edit_text(result)
    except Exception as e:
        await thinking_msg.edit_text(f"Error: {e}")
