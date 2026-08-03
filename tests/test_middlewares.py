from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.middlewares import UserTrackerMiddleware
from bot.models import User

pytestmark = pytest.mark.usefixtures("clean_db")


def _tg_user(uid, username):
    return SimpleNamespace(id=uid, username=username)


async def test_creates_user_on_first_seen(mongo_db):
    handler = AsyncMock(return_value="ok")
    event = object()
    data = {"event_from_user": _tg_user(1, "Bob")}

    result = await UserTrackerMiddleware()(handler, event, data)

    assert result == "ok"
    handler.assert_awaited_once_with(event, data)
    user = await User.find_one(User.user_id == 1)
    assert user.username == "bob"


async def test_updates_username_on_change(mongo_db):
    await User(user_id=1, username="bob").insert()
    data = {"event_from_user": _tg_user(1, "bobby")}

    await UserTrackerMiddleware()(AsyncMock(), object(), data)

    user = await User.find_one(User.user_id == 1)
    assert user.username == "bobby"


async def test_steals_username_from_stale_owner(mongo_db):
    """A username that changed hands must not stay claimed by its old owner."""
    await User(user_id=1, username="bob").insert()
    data = {"event_from_user": _tg_user(2, "bob")}

    await UserTrackerMiddleware()(AsyncMock(), object(), data)

    old_owner = await User.find_one(User.user_id == 1)
    new_owner = await User.find_one(User.user_id == 2)
    assert old_owner.username is None
    assert new_owner.username == "bob"


async def test_clears_username_when_removed_on_telegram(mongo_db):
    await User(user_id=1, username="bob").insert()
    data = {"event_from_user": _tg_user(1, None)}

    await UserTrackerMiddleware()(AsyncMock(), object(), data)

    user = await User.find_one(User.user_id == 1)
    assert user.username is None
