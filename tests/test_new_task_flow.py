from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot.enums import Messages
from bot.handlers.new_task import (
    NewTask,
    category_custom_prompt,
    category_custom_set,
    category_picked,
    category_skipped,
    cmd_cancel,
    cmd_new,
    deadline_back,
    deadline_none,
    deadline_shortcut,
    new_task_content_invalid,
    new_task_deadline,
    new_task_deadline_invalid,
    new_task_photo,
    new_task_text,
    pool_picked,
    repeat_back,
    repeat_days_prompt,
    repeat_days_set,
    repeat_none,
    repeat_weekday_toggle,
    repeat_weekdays_confirm,
    repeat_weekdays_prompt,
    weekdays_back,
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
    callback.message.delete = AsyncMock()
    return callback


async def test_cmd_new_asks_timezone_for_new_user(mongo_db):
    state = _fsm(7)
    message = _message(uid=7)

    await cmd_new(message, state)

    message.answer.assert_awaited_once_with(Messages.ASK_TIMEZONE)
    assert await state.get_state() != NewTask.waiting_content


async def test_cmd_new_prompts_known_user(mongo_db):
    await User(user_id=7, utc_offset_minutes=0).insert()
    state = _fsm(7)
    message = _message(uid=7)

    await cmd_new(message, state)

    message.answer.assert_awaited_once_with(Messages.NEW_TASK_PROMPT)
    assert await state.get_state() == NewTask.waiting_content


async def test_new_task_content_invalid_fallback(mongo_db):
    await new_task_content_invalid(_message(uid=1))


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


async def test_deadline_shortcut_rejects_unknown_key(mongo_db):
    """Regression: a forged callback_data (not one of the real shortcut
    buttons) must not raise KeyError out of DEADLINE_SHORTCUTS."""
    state = _fsm()
    await state.set_state(NewTask.waiting_deadline)

    due_cb = _callback(1, "due:not_a_real_shortcut")
    await deadline_shortcut(due_cb, state)

    assert await state.get_state() == NewTask.waiting_deadline
    assert (await state.get_data()).get("due_at") is None
    due_cb.answer.assert_awaited_once()


async def test_category_picked_rejects_too_long_category(mongo_db):
    """Regression: a forged callback_data can carry an arbitrarily long
    category, which would otherwise blow past the 64-byte callback_data
    limit and break the category keyboard for the whole household."""
    state = _fsm()
    await state.set_state(NewTask.waiting_category)

    long_category = "x" * 100
    cb = _callback(1, f"cat:{long_category}")
    await category_picked(cb, state)

    assert (await state.get_data()).get("category") is None
    cb.answer.assert_awaited_once()


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


async def test_repeat_weekday_toggle_rejects_non_int(mongo_db):
    state = _fsm(user_id=2)
    await state.set_state(NewTask.waiting_repeat_weekdays)
    await state.update_data(selected_weekdays=[])

    cb = _callback(2, "wd:not_a_number")
    await repeat_weekday_toggle(cb, state)

    assert (await state.get_data())["selected_weekdays"] == []
    cb.answer.assert_awaited_once()


async def test_repeat_weekday_toggle_rejects_out_of_range(mongo_db):
    """Regression: an out-of-range index must not slip into selected_
    weekdays, or WEEKDAY_NAMES[i] raises IndexError once "Done" is hit."""
    state = _fsm(user_id=2)
    await state.set_state(NewTask.waiting_repeat_weekdays)
    await state.update_data(selected_weekdays=[])

    cb = _callback(2, "wd:99")
    await repeat_weekday_toggle(cb, state)

    assert (await state.get_data())["selected_weekdays"] == []
    cb.answer.assert_awaited_once()


async def test_repeat_days_creates_task(mongo_db):
    state = _fsm(user_id=3)
    await state.update_data(text="water plants")
    await state.set_state(NewTask.waiting_repeat_days)

    await repeat_days_set(_message(uid=3, text="3"), state)

    assert await state.get_state() is None
    task = await Task.find_one(Task.user_id == 3)
    assert task.repeat_every_days == 3


async def test_category_picked_from_top(mongo_db):
    state = _fsm(1)
    await state.update_data(text="chore")
    await state.set_state(NewTask.waiting_category)

    await category_picked(_callback(1, "cat:kitchen"), state)

    assert await state.get_state() == NewTask.waiting_deadline
    assert (await state.get_data())["category"] == "kitchen"


async def test_category_custom_prompt(mongo_db):
    state = _fsm(1)
    await state.set_state(NewTask.waiting_category)

    await category_custom_prompt(_callback(1, "cat_custom"), state)

    assert await state.get_state() == NewTask.waiting_category_custom


async def test_deadline_back_returns_to_category(mongo_db):
    state = _fsm(1)
    await state.set_state(NewTask.waiting_deadline)

    await deadline_back(_callback(1, "nav_back"), state)

    assert await state.get_state() == NewTask.waiting_category


async def test_new_task_deadline_none_via_text(mongo_db):
    state = _fsm(1)
    await state.update_data(text="chore")
    await state.set_state(NewTask.waiting_deadline)

    await new_task_deadline(_message(uid=1, text="нет"), state)

    task = await Task.find_one(Task.user_id == 1)
    assert task.due_at is None
    assert await state.get_state() is None


async def test_new_task_deadline_invalid_format(mongo_db):
    state = _fsm(1)
    await state.set_state(NewTask.waiting_deadline)

    await new_task_deadline(_message(uid=1, text="not a date"), state)

    assert await state.get_state() == NewTask.waiting_deadline


async def test_new_task_deadline_invalid_fallback(mongo_db):
    await new_task_deadline_invalid(_message(uid=1))


async def test_repeat_days_prompt(mongo_db):
    state = _fsm(1)
    await state.set_state(NewTask.waiting_repeat)

    await repeat_days_prompt(_callback(1, "repeat_days"), state)

    assert await state.get_state() == NewTask.waiting_repeat_days


async def test_repeat_back_returns_to_deadline(mongo_db):
    state = _fsm(1)
    await state.set_state(NewTask.waiting_repeat)

    await repeat_back(_callback(1, "nav_back"), state)

    assert await state.get_state() == NewTask.waiting_deadline


async def test_repeat_days_set_invalid_number(mongo_db):
    state = _fsm(1)
    await state.update_data(text="chore")
    await state.set_state(NewTask.waiting_repeat_days)

    await repeat_days_set(_message(uid=1, text="not-a-number"), state)

    assert await state.get_state() == NewTask.waiting_repeat_days
    assert await Task.find_one(Task.user_id == 1) is None


async def test_repeat_weekdays_confirm_requires_selection(mongo_db):
    state = _fsm(1)
    await state.set_state(NewTask.waiting_repeat_weekdays)
    await state.update_data(selected_weekdays=[])
    callback = _callback(1, "wd_done")

    await repeat_weekdays_confirm(callback, state)

    assert await state.get_state() == NewTask.waiting_repeat_weekdays
    callback.answer.assert_awaited_once_with(
        Messages.PICK_AT_LEAST_ONE_DAY, show_alert=True
    )


async def test_weekdays_back_returns_to_repeat(mongo_db):
    state = _fsm(1)
    await state.set_state(NewTask.waiting_repeat_weekdays)

    await weekdays_back(_callback(1, "nav_back"), state)

    assert await state.get_state() == NewTask.waiting_repeat


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


async def test_pool_picked_rejects_non_member_pool(mongo_db):
    """Regression: a forged pool_id in callback_data must not let a task
    be attached to a pool its owner was never invited to."""
    other_pool = await Pool(
        name="Not yours", members=[2], created_by=2
    ).insert()
    state = _fsm(user_id=5)
    await state.set_state(NewTask.waiting_pool)
    await state.update_data(text="fix sink", photo_file_id=None)

    forged_cb = _callback(5, f"task_pool:{other_pool.id}")
    await pool_picked(forged_cb, state)

    assert await state.get_state() == NewTask.waiting_pool
    assert (await state.get_data()).get("pool_id") is None
    forged_cb.answer.assert_awaited_once_with(
        Messages.POOL_NOT_FOUND, show_alert=True
    )


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
