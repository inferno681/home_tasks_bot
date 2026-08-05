from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot.enums import Messages, TaskStatus
from bot.handlers.history import cb_history_page, cmd_history
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
    return message


def _callback(uid, data):
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = SimpleNamespace(id=uid)
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    return callback


async def _done_task(uid, n, **kwargs):
    completed = datetime(2030, 1, n, tzinfo=timezone.utc)
    return await Task(
        user_id=uid,
        text=f"task {n}",
        status=TaskStatus.DONE,
        completed_at=completed,
        **kwargs,
    ).insert()


async def test_history_asks_timezone_for_new_user(mongo_db):
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    message.answer.assert_awaited_once_with(Messages.ASK_TIMEZONE)


async def test_history_shows_empty_message(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    message.answer.assert_awaited_once_with(
        Messages.HISTORY_EMPTY, reply_markup=None
    )


async def test_history_ignores_open_tasks(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await Task(user_id=1, text="still open").insert()
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    message.answer.assert_awaited_once_with(
        Messages.HISTORY_EMPTY, reply_markup=None
    )


async def test_history_ignores_deleted_tasks(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await _done_task(1, 1, deleted_at=datetime.now(timezone.utc))
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    message.answer.assert_awaited_once_with(
        Messages.HISTORY_EMPTY, reply_markup=None
    )


async def test_history_shows_first_page_no_nav_when_single_page(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await _done_task(1, 1, category="garden")
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    call = message.answer.await_args
    text, kwargs = call.args[0], call.kwargs
    assert "task 1" in text
    assert "garden" in text
    assert "01.01.2030" in text
    assert kwargs["reply_markup"] is None


async def test_history_shows_next_button_when_more_pages(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    for n in range(1, 7):  # 6 done tasks, page size 5 -> 2 pages
        await _done_task(1, n)
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    kb = message.answer.await_args.kwargs["reply_markup"]
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert buttons == ["hist:1"]


async def test_history_sorted_most_recent_first(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await _done_task(1, 1)
    await _done_task(1, 2)
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    text = message.answer.await_args.args[0]
    assert text.index("task 2") < text.index("task 1")


async def test_history_excludes_other_users_personal_tasks(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await _done_task(2, 1)
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    message.answer.assert_awaited_once_with(
        Messages.HISTORY_EMPTY, reply_markup=None
    )


async def test_history_includes_shared_task(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await _done_task(2, 1, shared_with=[1])
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    text = message.answer.await_args.args[0]
    assert "task 1" in text


async def test_history_includes_pool_task(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    pool = await Pool(name="Family", members=[1, 2], created_by=2).insert()
    await _done_task(2, 1, pool_id=pool.id)
    message = _message(uid=1)
    state = _fsm(1)

    await cmd_history(message, state)

    text = message.answer.await_args.args[0]
    assert "task 1" in text


async def test_history_page_callback_shows_prev_button(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    for n in range(1, 7):
        await _done_task(1, n)
    callback = _callback(1, "hist:1")

    await cb_history_page(callback)

    callback.message.edit_text.assert_awaited_once()
    call = callback.message.edit_text.await_args
    kb = call.kwargs["reply_markup"]
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert buttons == ["hist:0"]
    assert "task 1" in call.args[0]


async def test_history_page_callback_out_of_range_shows_empty(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await _done_task(1, 1)
    callback = _callback(1, "hist:5")

    await cb_history_page(callback)

    callback.message.edit_text.assert_awaited_once_with(
        Messages.HISTORY_EMPTY, reply_markup=None
    )


async def test_history_page_callback_rejects_malformed_page(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await _done_task(1, 1)
    callback = _callback(1, "hist:not_a_number")

    await cb_history_page(callback)

    callback.answer.assert_awaited_once()
    callback.message.edit_text.assert_not_awaited()


async def test_history_page_callback_rejects_negative_page(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    await _done_task(1, 1)
    callback = _callback(1, "hist:-1")

    await cb_history_page(callback)

    callback.answer.assert_awaited_once()
    callback.message.edit_text.assert_not_awaited()
