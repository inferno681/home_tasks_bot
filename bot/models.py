from datetime import datetime, timezone
from typing import List, Optional

from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field

from bot.enums import TaskStatus


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
    # None = личная задача, видна только user_id (+ shared_with)
    pool_id: Optional[PydanticObjectId] = None

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

    # Пул, в который попадают новые задачи по умолчанию; None = личные.
    default_pool_id: Optional[PydanticObjectId] = None
    # Спрашивать пул явно при /new, а не молча брать default_pool_id.
    ask_pool_on_create: bool = False

    class Settings:
        name = "users"


class Pool(Document):
    name: str
    members: List[int] = Field(default_factory=list)
    created_by: int

    class Settings:
        name = "pools"

    @property
    def short_id(self) -> str:
        """Last 6 hex chars of the id — enough to disambiguate same-named
        pools without asking the user to paste a full ObjectId."""
        return str(self.id)[-6:]

    @property
    def label(self) -> str:
        return f"{self.name} #{self.short_id}"
