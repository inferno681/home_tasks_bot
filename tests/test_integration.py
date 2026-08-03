from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.pymongo import PyMongoStorage
from beanie.operators import AddToSet, Set

from bot.enums import TaskStatus
from bot.handlers.list_tasks import _open_tasks_for
from bot.models import Task
from bot.scheduler import check_reminders

pytestmark = pytest.mark.usefixtures("clean_db")


async def test_open_tasks_includes_owned_and_shared(mongo_db):
    owned = await Task(user_id=1, text="mine").insert()
    shared = await Task(
        user_id=2, text="shared with me", shared_with=[1]
    ).insert()
    someone_elses = await Task(user_id=2, text="not mine").insert()

    tasks = await _open_tasks_for(uid=1)

    ids = {task.id for task in tasks}
    assert owned.id in ids
    assert shared.id in ids
    assert someone_elses.id not in ids


async def test_open_tasks_filters_by_category(mongo_db):
    kitchen = await Task(user_id=1, text="dishes", category="kitchen").insert()
    await Task(user_id=1, text="mow", category="garden").insert()

    tasks = await _open_tasks_for(uid=1, category="kitchen")

    assert [task.id for task in tasks] == [kitchen.id]


async def test_open_tasks_excludes_done(mongo_db):
    done = await Task(
        user_id=1, text="already done", status=TaskStatus.DONE
    ).insert()

    tasks = await _open_tasks_for(uid=1)

    assert done.id not in {task.id for task in tasks}


async def test_check_reminders_ignores_tasks_without_due_date(mongo_db):
    """Tasks without a deadline must never trigger a reminder."""
    no_deadline = await Task(
        user_id=1, text="no deadline", due_at=None
    ).insert()
    overdue = await Task(
        user_id=1,
        text="overdue",
        due_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    ).insert()

    fake_bot = AsyncMock()
    await check_reminders(fake_bot)

    fake_bot.send_message.assert_called_once()
    assert fake_bot.send_message.call_args[0][0] == 1

    assert (await Task.get(no_deadline.id)).reminded is False
    assert (await Task.get(overdue.id)).reminded is True


async def test_check_reminders_keeps_reminded_false_on_send_failure(mongo_db):
    """Failed sends must retry next tick, not get marked as delivered."""
    task = await Task(
        user_id=1,
        text="will fail to send",
        due_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    ).insert()

    fake_bot = AsyncMock()
    fake_bot.send_message.side_effect = RuntimeError("boom")
    await check_reminders(fake_bot)

    assert (await Task.get(task.id)).reminded is False


async def test_atomic_updates_survive_concurrent_stale_reads(mongo_db):
    """Regression guard for the task.save() full-document-overwrite bug:
    two independently-fetched (stale) copies of the same task must both be
    able to land their atomic changes without clobbering each other.
    """
    task = await Task(user_id=1, text="race target").insert()

    session_a = await Task.get(task.id)
    session_b = await Task.get(task.id)

    await session_a.update(AddToSet({Task.shared_with: 2}))
    await session_b.update(Set({Task.assigned_to: 3}))

    refreshed = await Task.get(task.id)
    assert refreshed.shared_with == [2]
    assert refreshed.assigned_to == 3


async def test_pymongo_fsm_storage_roundtrip(mongo_db):
    """The `mongo` FSM storage option actually persists state/data."""
    storage = PyMongoStorage(
        client=mongo_db.client,
        db_name=mongo_db.name,
        collection_name="fsm_states_test",
    )
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)

    await storage.set_state(key, "waiting_offset")
    assert await storage.get_state(key) == "waiting_offset"

    await storage.set_data(key, {"category": "kitchen"})
    assert await storage.get_data(key) == {"category": "kitchen"}

    await storage.set_state(key, None)
    assert await storage.get_state(key) is None
