import pytest

from bot.task_access import get_task

pytestmark = pytest.mark.usefixtures("clean_db")


async def test_get_task_returns_none_for_malformed_id(mongo_db):
    assert await get_task("not-a-valid-object-id") is None
