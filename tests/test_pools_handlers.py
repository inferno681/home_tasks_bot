from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Message

from bot.enums import Messages
from bot.handlers.pools import (
    cb_pool_invite_accept,
    cb_pool_invite_decline,
    cmd_invite,
    cmd_kick,
    cmd_leave,
    cmd_newpool,
    cmd_pools,
)
from bot.models import Pool, User

pytestmark = pytest.mark.usefixtures("clean_db")


def _message(uid):
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=uid)
    message.answer = AsyncMock()
    message.bot = MagicMock()
    message.bot.send_message = AsyncMock()
    message.bot.get_me = AsyncMock(
        return_value=SimpleNamespace(username="testbot")
    )
    return message


def _callback(uid, data):
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = SimpleNamespace(id=uid)
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.bot = MagicMock()
    callback.bot.send_message = AsyncMock()
    return callback


async def test_newpool_requires_name(mongo_db):
    message = _message(1)

    await cmd_newpool(message, CommandObject(command="newpool", args=""))

    message.answer.assert_awaited_once_with(Messages.POOL_FORMAT_NEW)


async def test_newpool_confirmation_includes_short_id(mongo_db):
    message = _message(1)

    await cmd_newpool(
        message, CommandObject(command="newpool", args="Семья")
    )

    pool = await Pool.find_one(Pool.name == "Семья")
    message.answer.assert_awaited_once_with(
        Messages.POOL_CREATED.format(name="Семья", short_id=pool.short_id)
    )


async def test_newpool_creates_pool_with_creator_as_member(mongo_db):
    message = _message(1)

    await cmd_newpool(
        message, CommandObject(command="newpool", args="Семья")
    )

    pool = await Pool.find_one(Pool.name == "Семья")
    assert pool.members == [1]
    assert pool.created_by == 1


async def test_invite_requires_pool_and_username(mongo_db):
    message = _message(1)

    await cmd_invite(message, CommandObject(command="invite", args="Семья"))

    message.answer.assert_awaited_once_with(Messages.POOL_FORMAT_INVITE)


async def test_invite_rejects_unknown_pool(mongo_db):
    await User(user_id=2, username="bob").insert()
    message = _message(1)

    await cmd_invite(
        message, CommandObject(command="invite", args="Семья @bob")
    )

    message.answer.assert_awaited_once_with(Messages.POOL_NOT_FOUND)


async def test_invite_rejects_unregistered_target(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    message = _message(1)

    await cmd_invite(
        message, CommandObject(command="invite", args="Семья @ghost")
    )

    text = message.answer.await_args.args[0]
    assert f"https://t.me/testbot?start=pool_{pool.id}_1" in text


async def test_invite_rejects_existing_member(mongo_db):
    await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    await User(user_id=2, username="bob").insert()
    message = _message(1)

    await cmd_invite(
        message, CommandObject(command="invite", args="Семья @bob")
    )

    message.answer.assert_awaited_once_with(
        Messages.POOL_ALREADY_MEMBER.format(pool="Семья")
    )


async def test_invite_sends_request_to_target(mongo_db):
    await Pool(name="Семья", members=[1], created_by=1).insert()
    await User(user_id=2, username="bob").insert()
    message = _message(1)

    await cmd_invite(
        message, CommandObject(command="invite", args="Семья @Bob")
    )

    send_message = message.bot.send_message
    send_message.assert_awaited_once()
    assert send_message.await_args.args[0] == 2
    message.answer.assert_awaited_once_with(
        Messages.POOL_INVITE_SENT.format(pool="Семья", username="bob")
    )


async def test_pools_lists_membership(mongo_db):
    await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    await Pool(name="Дача", members=[1], created_by=1).insert()
    message = _message(1)

    await cmd_pools(message)

    text = message.answer.await_args.args[0]
    assert "Семья" in text
    assert "Дача" in text


async def test_pools_lists_short_id_for_each_pool(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    message = _message(1)

    await cmd_pools(message)

    text = message.answer.await_args.args[0]
    assert f"#{pool.short_id}" in text


async def test_invite_same_name_without_id_is_ambiguous(mongo_db):
    await Pool(name="Дача", members=[1], created_by=1).insert()
    await Pool(name="Дача", members=[1], created_by=1).insert()
    await User(user_id=2, username="bob").insert()
    message = _message(1)

    await cmd_invite(
        message, CommandObject(command="invite", args="Дача @bob")
    )

    text = message.answer.await_args.args[0]
    assert "Дача" in text
    message.bot.send_message.assert_not_awaited()


async def test_invite_with_short_id_disambiguates(mongo_db):
    pool_a = await Pool(name="Дача", members=[1], created_by=1).insert()
    await Pool(name="Дача", members=[1], created_by=1).insert()
    await User(user_id=2, username="bob").insert()
    message = _message(1)

    await cmd_invite(
        message,
        CommandObject(
            command="invite", args=f"Дача #{pool_a.short_id} @bob"
        ),
    )

    message.bot.send_message.assert_awaited_once()
    message.answer.assert_awaited_once_with(
        Messages.POOL_INVITE_SENT.format(pool="Дача", username="bob")
    )


async def test_leave_same_name_without_id_is_ambiguous(mongo_db):
    pool_a = await Pool(name="Дача", members=[1], created_by=1).insert()
    pool_b = await Pool(name="Дача", members=[1], created_by=1).insert()
    message = _message(1)

    await cmd_leave(message, CommandObject(command="leave", args="Дача"))

    text = message.answer.await_args.args[0]
    assert "Дача" in text
    assert await Pool.get(pool_a.id) is not None
    assert await Pool.get(pool_b.id) is not None


async def test_leave_with_short_id_removes_the_right_pool(mongo_db):
    pool_a = await Pool(name="Дача", members=[1], created_by=1).insert()
    pool_b = await Pool(name="Дача", members=[1], created_by=1).insert()
    message = _message(1)

    await cmd_leave(
        message,
        CommandObject(command="leave", args=f"Дача #{pool_a.short_id}"),
    )

    assert await Pool.get(pool_a.id) is None
    assert await Pool.get(pool_b.id) is not None


async def test_pools_empty_message(mongo_db):
    message = _message(1)

    await cmd_pools(message)

    message.answer.assert_awaited_once_with(Messages.POOL_LIST_EMPTY)


async def test_accept_adds_member_to_pool(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    await User(user_id=2, username="bob").insert()
    callback = _callback(2, f"pool_yes:{pool.id}:1")

    await cb_pool_invite_accept(callback)

    refreshed = await Pool.get(pool.id)
    assert set(refreshed.members) == {1, 2}
    callback.message.edit_text.assert_awaited_once_with(
        Messages.POOL_JOINED.format(pool="Семья"), reply_markup=None
    )
    send_message = callback.bot.send_message
    send_message.assert_awaited_once()
    assert send_message.await_args.args[0] == 1


async def test_accept_rejects_forged_requester(mongo_db):
    """Regression: joining must re-check the requester is a real pool
    member, not trust whatever id is embedded in the callback_data —
    otherwise anyone who knows a pool_id could self-join by crafting a
    /start deep-link claiming to be inviting themselves."""
    pool = await Pool(name="Victim Family", members=[1], created_by=1).insert()
    attacker_id = 999
    callback = _callback(attacker_id, f"pool_yes:{pool.id}:{attacker_id}")

    await cb_pool_invite_accept(callback)

    refreshed = await Pool.get(pool.id)
    assert attacker_id not in refreshed.members
    callback.answer.assert_awaited_once_with(
        Messages.INVITE_EXPIRED, show_alert=True
    )


async def test_accept_rejects_malformed_pool_id(mongo_db):
    """Regression: a hand-crafted callback_data with a garbage pool id must
    not raise InvalidId — it should be treated like an expired invite."""
    callback = _callback(2, "pool_yes:not-an-object-id:1")

    await cb_pool_invite_accept(callback)

    callback.answer.assert_awaited_once_with(
        Messages.INVITE_EXPIRED, show_alert=True
    )


async def test_accept_rejects_malformed_requester_id(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    callback = _callback(2, f"pool_yes:{pool.id}:not-an-int")

    await cb_pool_invite_accept(callback)

    refreshed = await Pool.get(pool.id)
    assert refreshed.members == [1]
    callback.answer.assert_awaited_once_with(
        Messages.INVITE_EXPIRED, show_alert=True
    )


async def test_decline_does_not_add_member(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    callback = _callback(2, f"pool_no:{pool.id}:1")

    await cb_pool_invite_decline(callback)

    refreshed = await Pool.get(pool.id)
    assert refreshed.members == [1]
    callback.message.edit_text.assert_awaited_once_with(
        Messages.POOL_DECLINED, reply_markup=None
    )
    callback.bot.send_message.assert_awaited_once()


async def test_decline_skips_notify_for_forged_requester(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    attacker_id = 999
    callback = _callback(2, f"pool_no:{pool.id}:{attacker_id}")

    await cb_pool_invite_decline(callback)

    callback.message.edit_text.assert_awaited_once_with(
        Messages.POOL_DECLINED, reply_markup=None
    )
    callback.bot.send_message.assert_not_awaited()


async def test_decline_rejects_malformed_pool_id(mongo_db):
    callback = _callback(2, "pool_no:not-an-object-id:1")

    await cb_pool_invite_decline(callback)

    callback.message.edit_text.assert_awaited_once_with(
        Messages.POOL_DECLINED, reply_markup=None
    )
    callback.bot.send_message.assert_not_awaited()


async def test_decline_rejects_malformed_requester_id(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    callback = _callback(2, f"pool_no:{pool.id}:not-an-int")

    await cb_pool_invite_decline(callback)

    callback.bot.send_message.assert_not_awaited()


async def test_accept_tolerates_unreachable_requester(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    callback = _callback(2, f"pool_yes:{pool.id}:1")
    callback.bot.send_message.side_effect = TelegramForbiddenError(
        method=MagicMock(), message="bot was blocked by the user"
    )

    await cb_pool_invite_accept(callback)

    refreshed = await Pool.get(pool.id)
    assert set(refreshed.members) == {1, 2}


async def test_leave_requires_pool_name(mongo_db):
    message = _message(1)

    await cmd_leave(message, CommandObject(command="leave", args=""))

    message.answer.assert_awaited_once_with(Messages.LEAVE_FORMAT)


async def test_leave_removes_member_but_keeps_pool(mongo_db):
    pool = await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    message = _message(2)

    await cmd_leave(message, CommandObject(command="leave", args="Семья"))

    refreshed = await Pool.get(pool.id)
    assert refreshed.members == [1]
    message.answer.assert_awaited_once_with(
        Messages.LEFT_POOL.format(pool="Семья")
    )


async def test_leave_deletes_pool_when_last_member_leaves(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    message = _message(1)

    await cmd_leave(message, CommandObject(command="leave", args="Семья"))

    assert await Pool.get(pool.id) is None


async def test_leave_clears_default_pool_if_it_was_this_one(mongo_db):
    """Regression: otherwise silent-default /new tasks would keep landing
    in a pool the user can no longer see (bot/handlers/new_task.py)."""
    pool = await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    await User(user_id=2, default_pool_id=pool.id).insert()
    message = _message(2)

    await cmd_leave(message, CommandObject(command="leave", args="Семья"))

    user = await User.find_one(User.user_id == 2)
    assert user.default_pool_id is None


async def test_leave_keeps_unrelated_default_pool(mongo_db):
    await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    other_pool = await Pool(name="Дача", members=[2], created_by=2).insert()
    await User(user_id=2, default_pool_id=other_pool.id).insert()
    message = _message(2)

    await cmd_leave(message, CommandObject(command="leave", args="Семья"))

    user = await User.find_one(User.user_id == 2)
    assert user.default_pool_id == other_pool.id


async def test_kick_requires_format(mongo_db):
    message = _message(1)

    await cmd_kick(message, CommandObject(command="kick", args=""))

    message.answer.assert_awaited_once_with(Messages.KICK_FORMAT)


async def test_kick_rejects_unknown_pool(mongo_db):
    await User(user_id=2, username="bob").insert()
    message = _message(1)

    await cmd_kick(
        message, CommandObject(command="kick", args="NoSuchPool @bob")
    )

    message.answer.assert_awaited_once_with(Messages.POOL_NOT_FOUND)


async def test_kick_requires_creator(mongo_db):
    await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    await User(user_id=2, username="bob").insert()
    message = _message(2)

    await cmd_kick(
        message, CommandObject(command="kick", args="Семья @bob")
    )

    message.answer.assert_awaited_once_with(Messages.KICK_CREATOR_ONLY)


async def test_kick_rejects_non_member(mongo_db):
    await Pool(name="Семья", members=[1], created_by=1).insert()
    await User(user_id=2, username="bob").insert()
    message = _message(1)

    await cmd_kick(
        message, CommandObject(command="kick", args="Семья @bob")
    )

    message.answer.assert_awaited_once_with(
        Messages.KICK_NOT_MEMBER.format(pool="Семья")
    )


async def test_kick_removes_member_and_notifies(mongo_db):
    pool = await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    await User(user_id=2, username="bob").insert()
    message = _message(1)

    await cmd_kick(
        message, CommandObject(command="kick", args="Семья @bob")
    )

    refreshed = await Pool.get(pool.id)
    assert refreshed.members == [1]
    message.answer.assert_awaited_once_with(
        Messages.KICK_SUCCESS.format(pool="Семья", username="bob")
    )
    send_message = message.bot.send_message
    send_message.assert_awaited_once()
    assert send_message.await_args.args[0] == 2


async def test_kick_clears_kicked_users_default_pool(mongo_db):
    pool = await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    await User(user_id=2, username="bob", default_pool_id=pool.id).insert()
    message = _message(1)

    await cmd_kick(
        message, CommandObject(command="kick", args="Семья @bob")
    )

    user = await User.find_one(User.user_id == 2)
    assert user.default_pool_id is None
