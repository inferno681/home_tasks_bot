from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from beanie.operators import Set

from bot.models import User


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
            await User.find_one(User.user_id == tg_user.id).upsert(
                Set({User.username: tg_user.username}),
                on_insert=User(user_id=tg_user.id, username=tg_user.username),
            )
        return await handler(event, data)
