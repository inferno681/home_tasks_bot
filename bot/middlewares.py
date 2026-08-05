from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject
from beanie.operators import Set

from bot.enums import Messages
from bot.models import User
from bot.safe_edit import safe_notify
from config.config import config


class UserTrackerMiddleware(BaseMiddleware):
    """Держит users.user_id/username свежими для поиска по @username."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is not None:
            username = tg_user.username.lower() if tg_user.username else None
            if username is not None:
                # Telegram username сменил владельца — снять его со старого
                # документа, иначе find_one(username==...) в /share и /assign
                # может найти не того (username больше не уникален).
                await User.find(
                    User.username == username, User.user_id != tg_user.id
                ).update(Set({User.username: None}))
            is_new = (
                await User.find_one(User.user_id == tg_user.id)
            ) is None
            await User.find_one(User.user_id == tg_user.id).upsert(
                Set({User.username: username}),
                on_insert=User(user_id=tg_user.id, username=username),
            )
            if is_new and config.secrets.admin_id:
                bot: Bot = data["bot"]
                await safe_notify(
                    bot,
                    config.secrets.admin_id,
                    Messages.ADMIN_NEW_USER.format(
                        username=username or tg_user.id, user_id=tg_user.id
                    ),
                )
        return await handler(event, data)
