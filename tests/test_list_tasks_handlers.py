from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot.enums import Messages, TaskStatus
from bot.handlers.list_tasks import (
    cb_assign_accept,
    cb_assign_decline,
    cb_delete,
    cb_done,
    cb_finish_recurring,
    cb_share_accept,
    cb_share_decline,
    cb_snooze_apply,
    cb_snooze_cancel,
    cb_snooze_start,
    cb_undelete,
    cmd_assign,
    cmd_list,
    cmd_share,
)
from bot.models import Pool, Task, User

pytestmark = pytest.mark.usefixtures("clean_db")


def _fsm(user_id=1):
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id),
    )


def _message(uid=1):
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=uid)
    message.answer = AsyncMock()
    message.answer_photo = AsyncMock()
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


async def test_list_asks_timezone_for_new_user(mongo_db):
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_list(message, state, CommandObject(command="list", args=""))

    message.answer.assert_awaited_once_with(Messages.ASK_TIMEZONE)


async def test_list_shows_no_open_tasks_message(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_list(message, state, CommandObject(command="list", args=""))

    message.answer.assert_awaited_once_with(Messages.NO_OPEN_TASKS)


async def test_list_shows_full_task_card_without_photo(mongo_db):
    """Exercises _caption's every optional line at once: category, pool,
    due date, assignee, both repeat kinds, completed history."""
    await User(user_id=1, utc_offset_minutes=0).insert()
    await User(user_id=2, username="bob").insert()
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    due = datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)
    completed = datetime(2029, 1, 1, 10, 0, tzinfo=timezone.utc)
    await Task(
        user_id=1,
        text="water plants",
        category="garden",
        pool_id=pool.id,
        due_at=due,
        assigned_to=2,
        repeat_every_days=3,
        repeat_weekdays=[0, 2],
        completed_history=[completed],
    ).insert()
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_list(message, state, CommandObject(command="list", args=""))

    message.answer.assert_awaited_once()
    caption = message.answer.await_args.args[0]
    assert "garden" in caption
    assert "Семья" in caption
    assert "@bob" in caption


async def test_list_shows_task_with_photo(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await Task(
        user_id=1, text="chore", photo_file_id="photo123"
    ).insert()
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_list(message, state, CommandObject(command="list", args=""))

    message.answer_photo.assert_awaited_once()
    assert message.answer_photo.await_args.args[0] == "photo123"
    message.answer.assert_not_awaited()


async def test_share_requires_ownership(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    await User(user_id=2, username="bob").insert()
    message = _message(uid=2)

    await cmd_share(
        message, CommandObject(command="share", args=f"{task.id} @bob")
    )

    message.answer.assert_awaited_once_with(Messages.SHARE_OWNER_ONLY)
    assert (await Task.get(task.id)).shared_with == []


async def test_share_requires_format(mongo_db):
    message = _message(uid=1)

    await cmd_share(message, CommandObject(command="share", args=""))

    message.answer.assert_awaited_once_with(Messages.SHARE_FORMAT)


async def test_share_rejects_unknown_task(mongo_db):
    message = _message(uid=1)

    await cmd_share(
        message,
        CommandObject(
            command="share", args="000000000000000000000000 @bob"
        ),
    )

    message.answer.assert_awaited_once_with(Messages.TASK_NOT_FOUND)


async def test_share_already_shared(mongo_db):
    task = await Task(user_id=1, text="t", shared_with=[2]).insert()
    await User(user_id=2, username="bob").insert()
    message = _message(uid=1)

    await cmd_share(
        message, CommandObject(command="share", args=f"{task.id} @bob")
    )

    message.answer.assert_awaited_once_with(Messages.ALREADY_SHARED)


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


async def test_share_accept_rejects_malformed_requester_id(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"share_yes:{task.id}:not-an-int")

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


async def test_share_decline_rejects_malformed_requester_id(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"share_no:{task.id}:not-an-int")

    await cb_share_decline(callback)

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


async def test_assign_requires_format(mongo_db):
    message = _message(uid=1)

    await cmd_assign(message, CommandObject(command="assign", args=""))

    message.answer.assert_awaited_once_with(Messages.ASSIGN_FORMAT)


async def test_assign_rejects_unknown_task(mongo_db):
    message = _message(uid=1)

    await cmd_assign(
        message,
        CommandObject(
            command="assign", args="000000000000000000000000 @bob"
        ),
    )

    message.answer.assert_awaited_once_with(Messages.TASK_NOT_FOUND)


async def test_assign_requires_ownership(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    await User(user_id=2, username="bob").insert()
    message = _message(uid=2)

    await cmd_assign(
        message, CommandObject(command="assign", args=f"{task.id} @bob")
    )

    message.answer.assert_awaited_once_with(Messages.ASSIGN_OWNER_ONLY)


async def test_assign_unregistered_user_gets_deep_link(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    message = _message(uid=1)

    await cmd_assign(
        message, CommandObject(command="assign", args=f"{task.id} @ghost")
    )

    text = message.answer.await_args.args[0]
    assert f"https://t.me/testbot?start=assign_{task.id}_1" in text


async def test_assign_already_assigned(mongo_db):
    task = await Task(user_id=1, text="t", assigned_to=2).insert()
    await User(user_id=2, username="bob").insert()
    message = _message(uid=1)

    await cmd_assign(
        message, CommandObject(command="assign", args=f"{task.id} @bob")
    )

    message.answer.assert_awaited_once_with(Messages.ASSIGN_ALREADY)


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


async def test_assign_accept_rejects_malformed_requester_id(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"assign_yes:{task.id}:not-an-int")

    await cb_assign_accept(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.assigned_to is None
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


async def test_assign_decline_rejects_malformed_requester_id(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"assign_no:{task.id}:not-an-int")

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
    assert refreshed.completed_at is not None
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


async def test_delete_soft_deletes_task(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(1, f"delete:{task.id}")

    await cb_delete(callback)

    refreshed = await Task.get(task.id)
    assert refreshed is not None
    assert refreshed.deleted_at is not None
    callback.answer.assert_awaited_once_with(Messages.TASK_DELETED)
    callback.message.edit_reply_markup.assert_awaited_once()


async def test_delete_denies_non_authorized_user(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(2, f"delete:{task.id}")

    await cb_delete(callback)

    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )
    assert (await Task.get(task.id)).deleted_at is None


async def test_deleted_task_hidden_from_list(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    task = await Task(user_id=1, text="t").insert()
    await cb_delete(_callback(1, f"delete:{task.id}"))
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_list(message, state, CommandObject(command="list", args=""))

    message.answer.assert_awaited_once_with(Messages.NO_OPEN_TASKS)


async def test_undelete_restores_task(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    await cb_delete(_callback(1, f"delete:{task.id}"))
    callback = _callback(1, f"undelete:{task.id}")

    await cb_undelete(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.deleted_at is None
    callback.answer.assert_awaited_once_with(Messages.TASK_RESTORED)


async def test_undelete_denies_non_authorized_user(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    await cb_delete(_callback(1, f"delete:{task.id}"))
    callback = _callback(2, f"undelete:{task.id}")

    await cb_undelete(callback)

    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )
    assert (await Task.get(task.id)).deleted_at is not None


async def test_undelete_rejects_task_that_was_never_deleted(mongo_db):
    task = await Task(user_id=1, text="t").insert()
    callback = _callback(1, f"undelete:{task.id}")

    await cb_undelete(callback)

    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )


async def test_snooze_start_shows_shortcut_keyboard(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="t", due_at=due).insert()
    callback = _callback(1, f"snooze:{task.id}")

    await cb_snooze_start(callback)

    callback.message.edit_reply_markup.assert_awaited_once()
    call = callback.message.edit_reply_markup.await_args
    kb = call.kwargs["reply_markup"]
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert any(b.startswith(f"snz:{task.id}:") for b in buttons)


async def test_snooze_start_denies_non_authorized_user(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="t", due_at=due).insert()
    callback = _callback(2, f"snooze:{task.id}")

    await cb_snooze_start(callback)

    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )


async def test_snooze_apply_updates_due_at(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(
        user_id=1, text="t", due_at=due, reminded=True
    ).insert()
    callback = _callback(1, f"snz:{task.id}:1d")

    await cb_snooze_apply(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.due_at > due.replace(tzinfo=None)
    assert refreshed.reminded is False
    callback.answer.assert_awaited_once_with(
        Messages.TASK_SNOOZED.format(label="через 1 день")
    )


async def test_snooze_apply_denies_non_authorized_user(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="t", due_at=due).insert()
    callback = _callback(2, f"snz:{task.id}:1d")

    await cb_snooze_apply(callback)

    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )
    assert (await Task.get(task.id)).due_at == due.replace(tzinfo=None)


async def test_snooze_apply_rejects_unknown_shortcut(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="t", due_at=due).insert()
    callback = _callback(1, f"snz:{task.id}:not_a_real_key")

    await cb_snooze_apply(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.due_at == due.replace(tzinfo=None)
    callback.answer.assert_awaited_once()


async def test_snooze_cancel_restores_action_keyboard(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="t", due_at=due).insert()
    callback = _callback(1, f"snzback:{task.id}")

    await cb_snooze_cancel(callback)

    callback.message.edit_reply_markup.assert_awaited_once()
    call = callback.message.edit_reply_markup.await_args
    kb = call.kwargs["reply_markup"]
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert f"done:{task.id}" in buttons


async def test_snooze_cancel_denies_non_authorized_user(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="t", due_at=due).insert()
    callback = _callback(2, f"snzback:{task.id}")

    await cb_snooze_cancel(callback)

    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )


async def test_list_shows_finish_button_for_recurring_task(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    await Task(
        user_id=1, text="t", due_at=due, repeat_every_days=7
    ).insert()
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_list(message, state, CommandObject(command="list", args=""))

    kb = message.answer.await_args.kwargs["reply_markup"]
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert any(b.startswith("finish:") for b in buttons)


async def test_list_hides_finish_button_for_one_off_task(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await Task(user_id=1, text="t").insert()
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_list(message, state, CommandObject(command="list", args=""))

    kb = message.answer.await_args.kwargs["reply_markup"]
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert not any(b.startswith("finish:") for b in buttons)


async def test_finish_recurring_marks_status_done(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(
        user_id=1, text="t", due_at=due, repeat_every_days=7
    ).insert()
    callback = _callback(1, f"finish:{task.id}")

    await cb_finish_recurring(callback)

    refreshed = await Task.get(task.id)
    assert refreshed.status == TaskStatus.DONE
    assert refreshed.due_at == due.replace(tzinfo=None)
    assert refreshed.completed_at is not None
    callback.answer.assert_awaited_once_with(Messages.TASK_REPEAT_FINISHED)


async def test_finish_recurring_denies_non_authorized_user(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(
        user_id=1, text="t", due_at=due, repeat_every_days=7
    ).insert()
    callback = _callback(2, f"finish:{task.id}")

    await cb_finish_recurring(callback)

    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )
    assert (await Task.get(task.id)).status == TaskStatus.PENDING
