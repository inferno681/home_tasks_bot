from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from beanie import Document, Indexed
from pydantic import Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"


class Task(Document):
    user_id: int
    text: Optional[str] = None
    photo_file_id: Optional[str] = None
    due_at: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    reminded: bool = False  # чтобы не слать напоминание повторно
    shared_with: List[int] = Field(default_factory=list)

    category: Optional[str] = None
    assigned_to: Optional[int] = None

    # ровно одно из двух, либо ни одного — контролируется на уровне FSM
    repeat_every_days: Optional[int] = None
    repeat_weekdays: Optional[List[int]] = None  # 0=Пн..6=Вс

    completed_history: List[datetime] = Field(default_factory=list)

    class Settings:
        name = "tasks"


class User(Document):
    user_id: Indexed(int, unique=True)  # type: ignore[valid-type]
    username: Optional[str] = None
    utc_offset_minutes: Optional[int] = None  # None = ещё не спрошено

    class Settings:
        name = "users"
