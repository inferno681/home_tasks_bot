from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramForbiddenError

from bot.safe_edit import (
    safe_delete,
    safe_edit_reply_markup,
    safe_edit_text,
    safe_notify,
)


async def test_safe_edit_text_ignores_inaccessible_message():
    await safe_edit_text(None, "hi")  # must not raise


async def test_safe_edit_reply_markup_ignores_inaccessible_message():
    await safe_edit_reply_markup(None)  # must not raise


async def test_safe_delete_ignores_inaccessible_message():
    await safe_delete(None)  # must not raise


async def test_safe_notify_sends_message():
    bot = MagicMock()
    bot.send_message = AsyncMock()

    await safe_notify(bot, 1, "hi")

    bot.send_message.assert_awaited_once_with(1, "hi")


async def test_safe_notify_suppresses_delivery_failure():
    bot = MagicMock()
    bot.send_message = AsyncMock(
        side_effect=TelegramForbiddenError(
            method=MagicMock(), message="bot was blocked by the user"
        )
    )

    await safe_notify(bot, 1, "hi")  # must not raise
