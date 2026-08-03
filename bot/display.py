from typing import Optional, Union

from bot.models import User


def display_name(user: Optional[User], fallback: int) -> Union[str, int]:
    """Username if known, else the raw user_id as a fallback label."""
    return user.username if user and user.username else fallback
