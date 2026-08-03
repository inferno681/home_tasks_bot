from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Message

from bot.enums import Messages, TaskStatus
from bot.handlers.list_tasks import (
    cb_assign_accept,
    cb_assign_decline,
    cb_delete,
    cb_done,
    cb_share_accept,
    cb_share_decline,
    cmd_assign,
    cmd_share,
)
from bot.models import Task, User

pytestmark = pytest.mark.usefixtures("clean_db")


def _message(uid=1):
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
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.delete = AsyncMock()
    callback.bot = MagicMock()
    callback.bot.send_message = AsyncMock()
    return callback


async def test_share_requires_ownership(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    await User(user_id=2, username="bob").insert()
    message = _message(uid=2)

    await cmd_share(
        message, CommandObject(command="share", args=f"{task.id} @bob")
    )

    message.answer.assert_awaited_once_with(Messages.SHARE_OWNER_ONLY)
    assert (await Task.get(task.id)).shared_with == []


async def test_share_sends_confirm_request(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    await User(user_id=2, username="bob").insert()
    message = _message(uid=1)

    await cmd_share(
        message, CommandObject(command="share", args=f"{task.id} @Bob")
    )

    assert (await Task.get(task.id)).shared_with == []
    send_message = message.bot.send_message
    send_message.assert_awaited_once()
    assert send_message.await_args.args[0] == 2
    message.answer.assert_awaited_once_with(
        Messages.SHARE_REQUEST_SENT.format(username="bob")
    )


async def test_share_unregistered_user_gets_deep_link(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    message = _message(uid=1)

    await cmd_share(
        message, CommandObject(command="share", args=f"{task.id} @ghost")
    )

    text = message.answer.await_args.args[0]
    assert f"https://t.me/testbot?start=share_{task.id}_1" in text


async def test_share_accept_adds_to_shared_with(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"share_yes:{task.id}:1")

    await cb_share_accept(callback)

    assert (await Task.get(task.id)).shared_with == [2]
    callback.message.edit_text.assert_awaited_once_with(
        Messages.SHARE_ACCEPTED, reply_markup=None
    )


async def test_share_accept_rejects_forged_requester(mongo_db):
    """Regression: accepting must re-check the task's real owner, not trust
    whatever requester_id is embedded in the callback_data — otherwise
    anyone who knows a task_id could self-grant shared_with access by
    crafting a /start deep-link claiming to be the owner."""
    task = await Task(user_id=1, text="victim's task").insert()
    attacker_id = 999
    callback = _callback(attacker_id, f"share_yes:{task.id}:{attacker_id}")

    await cb_share_accept(callback)

    assert (await Task.get(task.id)).shared_with == []
    callback.answer.assert_awaited_once_with(
        Messages.INVITE_EXPIRED, show_alert=True
    )


async def test_share_decline_does_not_share(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"share_no:{task.id}:1")

    await cb_share_decline(callback)

    assert (await Task.get(task.id)).shared_with == []
    callback.message.edit_text.assert_awaited_once_with(
        Messages.SHARE_DECLINED, reply_markup=None
    )
    callback.bot.send_message.assert_awaited_once()


async def test_share_decline_skips_notify_for_forged_requester(mongo_db):
    """A decline for a task the claimed requester doesn't own must still
    close the card for the decliner, but must not notify the forged
    requester_id."""
    task = await Task(user_id=1, text="t").insert()
    attacker_id = 999
    callback = _callback(2, f"share_no:{task.id}:{attacker_id}")

    await cb_share_decline(callback)

    callback.message.edit_text.assert_awaited_once_with(
        Messages.SHARE_DECLINED, reply_markup=None
    )
    callback.bot.send_message.assert_not_awaited()


async def test_share_accept_tolerates_unreachable_requester(mongo_db):
    """If the real owner blocked the bot, the notify send fails but the
    share itself must still go through — no unhandled exception."""
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"share_yes:{task.id}:1")
    callback.bot.send_message.side_effect = TelegramForbiddenError(
        method=MagicMock(), message="bot was blocked by the user"
    )

    await cb_share_accept(callback)

    assert (await Task.get(task.id)).shared_with == [2]


async def test_assign_sends_confirm_request(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    await User(user_id=2, username="bob").insert()
    message = _message(uid=1)

    await cmd_assign(
        message, CommandObject(command="assign", args=f"{task.id} @bob")
    )

    refreshed = await Task.get(task.id)
    assert refreshed.assigned_to is None
    assert refreshed.shared_with == []
    message.answer.assert_awaited_once_with(
        Messages.ASSIGN_REQUEST_SENT.format(username="bob")
    )


async def test_assign_accept_sets_assignee_and_shares(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"assign_yes:{task.id}:1")

    await cb_assign_accept(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.assigned_to == 2
    assert refreshed.shared_with == [2]


async def test_assign_accept_rejects_forged_requester(mongo_db):
    task = await Task(user_id=1, text="victim's task").insert()
    attacker_id = 999
    callback = _callback(attacker_id, f"assign_yes:{task.id}:{attacker_id}")

    await cb_assign_accept(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.assigned_to is None
    assert refreshed.shared_with == []
    callback.answer.assert_awaited_once_with(
        Messages.INVITE_EXPIRED, show_alert=True
    )


async def test_assign_decline_does_not_assign(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"assign_no:{task.id}:1")

    await cb_assign_decline(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.assigned_to is None
    assert refreshed.shared_with == []
    callback.bot.send_message.assert_awaited_once()


async def test_assign_decline_skips_notify_for_forged_requester(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    attacker_id = 999
    callback = _callback(2, f"assign_no:{task.id}:{attacker_id}")

    await cb_assign_decline(callback)

    callback.bot.send_message.assert_not_awaited()


async def test_assign_accept_tolerates_unreachable_requester(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"assign_yes:{task.id}:1")
    callback.bot.send_message.side_effect = TelegramForbiddenError(
        method=MagicMock(), message="bot was blocked by the user"
    )

    await cb_assign_accept(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.assigned_to == 2


async def test_done_marks_status_for_one_off_task(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(1, f"done:{task.id}")

    await cb_done(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.status == TaskStatus.DONE
    callback.answer.assert_awaited_once_with(Messages.TASK_DONE)


async def test_done_reschedules_recurring_task(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(
        user_id=1, text="t", due_at=due, repeat_every_days=7
    ).insert()
    callback = _callback(1, f"done:{task.id}")

    await cb_done(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.status == TaskStatus.PENDING
    assert refreshed.due_at > due.replace(tzinfo=None)
    assert refreshed.reminded is False
    assert len(refreshed.completed_history) == 1


async def test_done_denies_non_authorized_user(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"done:{task.id}")

    await cb_done(callback)

    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )
    assert (await Task.get(task.id)).status == TaskStatus.PENDING


async def test_done_allows_shared_user(mongo_db):
    task = await Task(user_id=1, text="t", shared_with=[2]).insert()
    callback = _callback(2, f"done:{task.id}")

    await cb_done(callback)

    assert (await Task.get(task.id)).status == TaskStatus.DONE


async def test_delete_removes_task(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(1, f"delete:{task.id}")

    await cb_delete(callback)

    assert await Task.get(task.id) is None
    callback.message.delete.assert_awaited_once()
