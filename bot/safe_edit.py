from contextlib import suppress
from typing import Optional, Union

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import InaccessibleMessage, InlineKeyboardMarkup, Message

MaybeMessage = Union[Message, InaccessibleMessage, None]


async def safe_edit_text(
    message: MaybeMessage,
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Edit a bot message, tolerating races and inaccessible messages.

    `InaccessibleMessage` (old/deleted messages Telegram won't let the bot
    touch) has no edit/delete methods at all, and a double-tap on the same
    inline button can make the message vanish between the callback firing
    and us acting on it (TelegramBadRequest). Both are harmless no-ops here.
    """
    if not isinstance(message, Message):
        return
    with suppress(TelegramBadRequest):
        await message.edit_text(text, reply_markup=markup)


async def safe_edit_reply_markup(
    message: MaybeMessage, markup: Optional[InlineKeyboardMarkup] = None
) -> None:
    if not isinstance(message, Message):
        return
    with suppress(TelegramBadRequest):
        await message.edit_reply_markup(reply_markup=markup)


async def safe_delete(message: MaybeMessage) -> None:
    if not isinstance(message, Message):
        return
    with suppress(TelegramBadRequest):
        await message.delete()


async def safe_notify(bot: Bot, chat_id: int, text: str) -> None:
    """Message a user, tolerating delivery failure.

    The recipient may have blocked the bot, deactivated their account, or
    (for a value that only ever came from validated DB state, not raw
    input) simply never be reachable for other reasons — none of that
    should break the caller's already-applied accept/decline.
    """
    with suppress(TelegramAPIError):
        await bot.send_message(chat_id, text)
