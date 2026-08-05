from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.middlewares import UserTrackerMiddleware
from bot.models import User
from config.config import config

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


async def test_notifies_admin_on_new_user(mongo_db, monkeypatch):
    monkeypatch.setattr(config.secrets, "admin_id", 999)
    bot = AsyncMock()
    data = {"event_from_user": _tg_user(1, "bob"), "bot": bot}

    await UserTrackerMiddleware()(AsyncMock(return_value="ok"), object(), data)

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.args[0] == 999
    assert "bob" in bot.send_message.await_args.args[1]


async def test_no_admin_notification_without_admin_id(mongo_db, monkeypatch):
    monkeypatch.setattr(config.secrets, "admin_id", None)
    data = {"event_from_user": _tg_user(1, "bob")}  # no "bot" key at all

    result = await UserTrackerMiddleware()(
        AsyncMock(return_value="ok"), object(), data
    )

    assert result == "ok"


async def test_no_admin_notification_for_existing_user(mongo_db, monkeypatch):
    await User(user_id=1, username="bob").insert()
    monkeypatch.setattr(config.secrets, "admin_id", 999)
    bot = AsyncMock()
    data = {"event_from_user": _tg_user(1, "bobby"), "bot": bot}

    await UserTrackerMiddleware()(AsyncMock(), object(), data)

    bot.send_message.assert_not_awaited()
