from datetime import datetime, timedelta
from typing import List, Optional


def next_due_date(
    current_due: datetime,
    every_days: Optional[int] = None,
    weekdays: Optional[List[int]] = None,
) -> datetime:
    """Next occurrence for a recurring task.

    Exactly one of `every_days`/`weekdays` is expected; `weekdays` uses
    datetime.weekday() numbering (0=Monday..6=Sunday) and always advances at
    least one day, even if `current_due`'s weekday is itself selected.
    """
    if every_days is not None:
        return current_due + timedelta(days=every_days)

    if weekdays:
        for offset in range(1, 8):
            candidate = current_due + timedelta(days=offset)
            if candidate.weekday() in weekdays:
                return candidate

    raise ValueError("next_due_date requires every_days or weekdays")
