import pytest

from bot.categories import top_categories
from bot.models import Task

pytestmark = pytest.mark.usefixtures("clean_db")


async def test_top_categories_orders_by_usage_count(mongo_db):
    await Task(user_id=1, text="a", category="kitchen").insert()
    await Task(user_id=1, text="b", category="kitchen").insert()
    await Task(user_id=1, text="c", category="garden").insert()
    await Task(user_id=1, text="d", category=None).insert()

    top = await top_categories(limit=3)

    assert top == ["kitchen", "garden"]
