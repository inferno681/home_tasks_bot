from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.enums import TaskStatus
from bot.handlers.list_tasks import _open_tasks_for, cb_done
from bot.models import Pool, Task
from bot.scheduler import check_reminders

pytestmark = pytest.mark.usefixtures("clean_db")


def _callback(uid, data):
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = SimpleNamespace(id=uid)
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.edit_reply_markup = AsyncMock()
    return callback


async def test_personal_task_is_only_visible_to_owner(mongo_db):
    await Task(user_id=2, text="not mine").insert()

    tasks = await _open_tasks_for(uid=1)

    assert not tasks


async def test_pool_task_is_visible_to_all_members(mongo_db):
    await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    pool = await Pool.find_one(Pool.name == "Семья")
    theirs = await Task(user_id=2, text="pool chore", pool_id=pool.id).insert()

    tasks = await _open_tasks_for(uid=1)

    assert theirs.id in {task.id for task in tasks}


async def test_pool_task_is_invisible_to_non_members(mongo_db):
    pool = await Pool(name="Семья", members=[2], created_by=2).insert()
    await Task(user_id=2, text="pool chore", pool_id=pool.id).insert()

    tasks = await _open_tasks_for(uid=1)

    assert not tasks


async def test_pool_member_can_mark_done(mongo_db):
    pool = await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    task = await Task(user_id=1, text="chore", pool_id=pool.id).insert()
    callback = _callback(2, f"done:{task.id}")

    await cb_done(callback)

    assert (await Task.get(task.id)).status == TaskStatus.DONE


async def test_reminder_reaches_all_pool_members(mongo_db):
    pool = await Pool(name="Семья", members=[1, 2, 3], created_by=1).insert()
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    task = await Task(
        user_id=1, text="pool reminder", due_at=due, pool_id=pool.id
    ).insert()

    fake_bot = AsyncMock()
    await check_reminders(fake_bot)

    notified = {call.args[0] for call in fake_bot.send_message.await_args_list}
    assert notified == {1, 2, 3}
    assert (await Task.get(task.id)).reminded is True


async def test_personal_task_only_reminds_owner(mongo_db):
    due = datetime(2020, 1, 1, tzinfo=timezone.utc)
    await Task(user_id=1, text="personal reminder", due_at=due).insert()

    fake_bot = AsyncMock()
    await check_reminders(fake_bot)

    notified = {call.args[0] for call in fake_bot.send_message.await_args_list}
    assert notified == {1}
