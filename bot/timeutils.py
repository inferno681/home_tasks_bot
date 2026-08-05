from datetime import datetime, timedelta, timezone
from typing import Optional

from bot.constants import OFFSET_RE


def parse_utc_offset(text: str) -> Optional[int]:
    """Parse "+3"/"-5"/"+5:30" into minutes from UTC.

    Returns None if the text doesn't match the expected shape or the
    result falls outside the real-world -12:00..+14:00 range.
    """
    match = OFFSET_RE.match(text.strip())
    if not match:
        return None
    sign, hh, mm = match.groups()
    sign_multiplier = 1 if sign == "+" else -1
    total_minutes = int(hh) * 60 + int(mm or 0)
    offset_minutes = sign_multiplier * total_minutes
    if not -12 * 60 <= offset_minutes <= 14 * 60:
        return None
    return offset_minutes


def to_utc(local_naive: datetime, offset_minutes: int) -> datetime:
    return (local_naive - timedelta(minutes=offset_minutes)).replace(
        tzinfo=timezone.utc
    )


def to_local(dt_utc: datetime, offset_minutes: int) -> datetime:
    return dt_utc + timedelta(minutes=offset_minutes)


def user_offset(offset_minutes: Optional[int]) -> int:
    """Normalize a possibly-unset UTC offset (minutes) to 0."""
    return offset_minutes or 0


def is_quiet_hour(local_hour: int, start: int, end: int) -> bool:
    """Is `local_hour` (0-23) inside the [start, end) quiet window?

    Wraps past midnight when start > end (e.g. 22..8); start == end means
    quiet hours are effectively off (zero-width window).
    """
    if start == end:
        return False
    if start < end:
        return start <= local_hour < end
    return local_hour >= start or local_hour < end
