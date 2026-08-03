from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot.handlers.new_task import (
    NewTask,
    category_custom_set,
    category_skipped,
    cmd_cancel,
    deadline_none,
    deadline_shortcut,
    new_task_deadline,
    new_task_photo,
    new_task_text,
    pool_picked,
    repeat_days_set,
    repeat_none,
    repeat_weekday_toggle,
    repeat_weekdays_confirm,
    repeat_weekdays_prompt,
)
from bot.models import Pool, Task, User

pytestmark = pytest.mark.usefixtures("clean_db")


def _fsm(user_id=1):
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id),
    )


def _message(uid=1, text=None, photo=None, caption=None):
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=uid)
    message.text = text
    message.photo = photo
    message.caption = caption
    message.answer = AsyncMock()
    return message


def _callback(uid, data):
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = SimpleNamespace(id=uid)
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.answer = AsyncMock()
    return callback


async def test_full_flow_shortcut_deadline_no_repeat(mongo_db):
    state = _fsm()
    await state.set_state(NewTask.waiting_content)

    await new_task_text(_message(text="buy milk"), state)
    assert await state.get_state() == NewTask.waiting_category

    skip_cb = _callback(1, "cat_skip")
    await category_skipped(skip_cb, state)
    assert await state.get_state() == NewTask.waiting_deadline

    due_cb = _callback(1, "due:1d")
    await deadline_shortcut(due_cb, state)
    assert await state.get_state() == NewTask.waiting_repeat

    repeat_cb = _callback(1, "repeat_none")
    await repeat_none(repeat_cb, state)

    assert await state.get_state() is None
    task = await Task.find_one(Task.user_id == 1)
    assert task.text == "buy milk"
    assert task.category is None
    assert task.due_at is not None
    assert task.repeat_every_days is None


async def test_full_flow_photo_custom_category_weekday_repeat(mongo_db):
    state = _fsm(user_id=2)
    await state.set_state(NewTask.waiting_content)

    photo = [SimpleNamespace(file_id="small"), SimpleNamespace(file_id="big")]
    await new_task_photo(_message(uid=2, photo=photo, caption="do it"), state)
    assert await state.get_state() == NewTask.waiting_category

    await state.set_state(NewTask.waiting_category_custom)
    too_long = _message(uid=2, text="x" * 51)
    await category_custom_set(too_long, state)
    assert await state.get_state() == NewTask.waiting_category_custom

    await category_custom_set(_message(uid=2, text="garage"), state)
    assert await state.get_state() == NewTask.waiting_deadline

    manual_date = _message(uid=2, text="01.01.2030 10:00")
    await new_task_deadline(manual_date, state)
    assert await state.get_state() == NewTask.waiting_repeat

    weekdays_cb = _callback(2, "repeat_weekdays")
    await repeat_weekdays_prompt(weekdays_cb, state)
    assert await state.get_state() == NewTask.waiting_repeat_weekdays

    await repeat_weekday_toggle(_callback(2, "wd:0"), state)
    await repeat_weekday_toggle(_callback(2, "wd:2"), state)

    await repeat_weekdays_confirm(_callback(2, "wd_done"), state)

    assert await state.get_state() is None
    task = await Task.find_one(Task.user_id == 2)
    assert task.photo_file_id == "big"
    assert task.category == "garage"
    assert task.repeat_weekdays == [0, 2]


async def test_repeat_days_creates_task(mongo_db):
    state = _fsm(user_id=3)
    await state.update_data(text="water plants")
    await state.set_state(NewTask.waiting_repeat_days)

    await repeat_days_set(_message(uid=3, text="3"), state)

    assert await state.get_state() is None
    task = await Task.find_one(Task.user_id == 3)
    assert task.repeat_every_days == 3


async def test_ask_pool_on_create_inserts_pool_step(mongo_db):
    pool = await Pool(name="Семья", members=[5], created_by=5).insert()
    await User(user_id=5, ask_pool_on_create=True).insert()
    state = _fsm(user_id=5)
    await state.set_state(NewTask.waiting_content)

    await new_task_text(_message(uid=5, text="fix sink"), state)
    assert await state.get_state() == NewTask.waiting_pool

    pool_cb = _callback(5, f"task_pool:{pool.id}")
    await pool_picked(pool_cb, state)
    assert await state.get_state() == NewTask.waiting_category

    skip_cb = _callback(5, "cat_skip")
    await category_skipped(skip_cb, state)
    due_cb = _callback(5, "due_none")
    await deadline_none(due_cb, state)

    task = await Task.find_one(Task.user_id == 5)
    assert task.pool_id == pool.id


async def test_silent_default_pool_applies_without_asking(mongo_db):
    pool = await Pool(name="Семья", members=[6], created_by=6).insert()
    await User(
        user_id=6, ask_pool_on_create=False, default_pool_id=pool.id
    ).insert()
    state = _fsm(user_id=6)
    await state.set_state(NewTask.waiting_content)

    await new_task_text(_message(uid=6, text="water plants"), state)
    assert await state.get_state() == NewTask.waiting_category

    skip_cb = _callback(6, "cat_skip")
    await category_skipped(skip_cb, state)
    due_cb = _callback(6, "due_none")
    await deadline_none(due_cb, state)

    task = await Task.find_one(Task.user_id == 6)
    assert task.pool_id == pool.id


async def test_cancel_clears_state(mongo_db):
    state = _fsm(user_id=4)
    await state.set_state(NewTask.waiting_content)
    await state.update_data(text="abandoned")

    await cmd_cancel(_message(uid=4), state)

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert await Task.find_one(Task.user_id == 4) is None
