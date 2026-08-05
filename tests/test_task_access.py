from datetime import datetime, timezone

import pytest

from bot.models import Task
from bot.task_access import get_deleted_task, get_task

pytestmark = pytest.mark.usefixtures("clean_db")


async def test_get_task_returns_none_for_malformed_id(mongo_db):
    assert await get_task("not-a-valid-object-id") is None


async def test_get_task_hides_soft_deleted_task(mongo_db):
    task = await Task(
        user_id=1, text="t", deleted_at=datetime.now(timezone.utc)
    ).insert()

    assert await get_task(str(task.id)) is None


async def test_get_deleted_task_returns_none_for_malformed_id(mongo_db):
    assert await get_deleted_task("not-a-valid-object-id", 1) is None
