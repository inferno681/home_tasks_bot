from datetime import datetime, timedelta, timezone
from typing import Optional

from bot.models import User


def to_utc(local_naive: datetime, offset_minutes: int) -> datetime:
    return (local_naive - timedelta(minutes=offset_minutes)).replace(
        tzinfo=timezone.utc
    )


def to_local(dt_utc: datetime, offset_minutes: int) -> datetime:
    return dt_utc + timedelta(minutes=offset_minutes)


def user_offset(user: Optional[User]) -> int:
    """UTC offset for an already-fetched user, 0 if unset/missing."""
    if user and user.utc_offset_minutes:
        return user.utc_offset_minutes
    return 0
