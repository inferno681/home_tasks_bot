from typing import Optional, Union

from beanie import PydanticObjectId

from bot.enums import Messages
from bot.models import Pool, User


def display_name(user: Optional[User], fallback: int) -> Union[str, int]:
    """Username if known, else the raw user_id as a fallback label."""
    return user.username if user and user.username else fallback


async def pool_label(pool_id: Optional[PydanticObjectId]) -> str:
    """Pool name for display, or the "personal" label if unset/deleted."""
    if not pool_id:
        return Messages.POOL_PERSONAL_NAME
    pool = await Pool.get(pool_id)
    return pool.name if pool else Messages.POOL_PERSONAL_NAME
