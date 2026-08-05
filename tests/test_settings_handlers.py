from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.enums import Messages
from bot.handlers.settings import (
    cb_settings_set_pool,
    cb_settings_toggle_ask,
    cmd_settings,
)
from bot.models import Pool, User

pytestmark = pytest.mark.usefixtures("clean_db")


def _message(uid):
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=uid)
    message.answer = AsyncMock()
    return message


def _callback(uid, data):
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = SimpleNamespace(id=uid)
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    return callback


async def test_settings_shows_personal_by_default(mongo_db):
    await User(user_id=1).insert()
    message = _message(1)

    await cmd_settings(message)

    message.answer.assert_awaited_once()
    assert "Мои (личные)" in message.answer.await_args.args[0]


async def test_set_default_pool(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    await User(user_id=1).insert()
    callback = _callback(1, f"set_pool:{pool.id}")

    await cb_settings_set_pool(callback)

    user = await User.find_one(User.user_id == 1)
    assert user.default_pool_id == pool.id


async def test_set_default_pool_back_to_personal(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    await User(user_id=1, default_pool_id=pool.id).insert()
    callback = _callback(1, "set_pool:none")

    await cb_settings_set_pool(callback)

    user = await User.find_one(User.user_id == 1)
    assert user.default_pool_id is None


async def test_set_default_pool_rejects_non_member_pool(mongo_db):
    """Regression: a forged pool_id in callback_data must not attach a
    user's default pool to a pool they were never invited to — otherwise
    every task they create silently lands in a stranger's pool."""
    other_pool = await Pool(
        name="Not yours", members=[2], created_by=2
    ).insert()
    await User(user_id=1).insert()
    callback = _callback(1, f"set_pool:{other_pool.id}")

    await cb_settings_set_pool(callback)

    user = await User.find_one(User.user_id == 1)
    assert user.default_pool_id is None
    callback.answer.assert_awaited_once_with(
        Messages.POOL_NOT_FOUND, show_alert=True
    )


async def test_set_default_pool_rejects_malformed_id(mongo_db):
    await User(user_id=1).insert()
    callback = _callback(1, "set_pool:not-an-object-id")

    await cb_settings_set_pool(callback)

    user = await User.find_one(User.user_id == 1)
    assert user.default_pool_id is None
    callback.answer.assert_awaited_once_with(
        Messages.POOL_NOT_FOUND, show_alert=True
    )


async def test_toggle_ask_pool_on_create(mongo_db):
    await User(user_id=1, ask_pool_on_create=False).insert()
    callback = _callback(1, "set_ask_toggle")

    await cb_settings_toggle_ask(callback)

    user = await User.find_one(User.user_id == 1)
    assert user.ask_pool_on_create is True

    await cb_settings_toggle_ask(callback)
    user = await User.find_one(User.user_id == 1)
    assert user.ask_pool_on_create is False
