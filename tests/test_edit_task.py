from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot.enums import Messages
from bot.handlers.edit_task import (
    EditTask,
    cb_edit_cancel,
    cb_edit_field_picked,
    cb_edit_start,
    edit_category_custom_prompt,
    edit_category_custom_set,
    edit_category_picked,
    edit_category_skipped,
    edit_deadline_back,
    edit_deadline_invalid,
    edit_deadline_none,
    edit_deadline_shortcut,
    edit_deadline_text,
    edit_pool_picked,
    edit_repeat_back,
    edit_repeat_days_prompt,
    edit_repeat_days_set,
    edit_repeat_none,
    edit_repeat_weekday_toggle,
    edit_repeat_weekdays_confirm,
    edit_repeat_weekdays_prompt,
    edit_text_invalid,
    edit_text_photo,
    edit_text_text,
    edit_weekdays_back,
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


async def _editing(task_id, user_id=1):
    """FSM already parked in EditTask.waiting_field for this task."""
    state = _fsm(user_id)
    await state.set_state(EditTask.waiting_field)
    await state.update_data(edit_task_id=str(task_id))
    return state


async def test_edit_start_shows_menu_for_owner(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(1)
    callback = _callback(1, f"edit:{task.id}")

    await cb_edit_start(callback, state)

    assert await state.get_state() == EditTask.waiting_field
    callback.message.answer.assert_awaited_once()
    call_kwargs = callback.message.answer.await_args.kwargs
    assert call_kwargs["reply_markup"] is not None


async def test_edit_start_denies_stranger(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(2)
    callback = _callback(2, f"edit:{task.id}")

    await cb_edit_start(callback, state)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )


async def test_edit_start_allows_pool_member(mongo_db):
    pool = await Pool(name="Семья", members=[1, 2], created_by=1).insert()
    task = await Task(user_id=1, text="chore", pool_id=pool.id).insert()
    state = _fsm(2)
    callback = _callback(2, f"edit:{task.id}")

    await cb_edit_start(callback, state)

    assert await state.get_state() == EditTask.waiting_field


async def test_edit_cancel_clears_state(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = await _editing(task.id)
    callback = _callback(1, "edit_cancel")

    await cb_edit_cancel(callback, state)

    assert await state.get_state() is None
    callback.message.edit_text.assert_awaited_once_with(
        Messages.CANCELLED, reply_markup=None
    )


async def test_field_menu_routes_to_text_step(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = await _editing(task.id)
    callback = _callback(1, "editf:text")

    await cb_edit_field_picked(callback, state)

    assert await state.get_state() == EditTask.waiting_text


async def test_field_menu_blocks_repeat_without_deadline(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = await _editing(task.id)
    callback = _callback(1, "editf:repeat")

    await cb_edit_field_picked(callback, state)

    assert await state.get_state() == EditTask.waiting_field
    callback.answer.assert_awaited_once_with(
        Messages.EDIT_NEEDS_DEADLINE, show_alert=True
    )


async def test_edit_text_via_plain_text_clears_photo(mongo_db):
    task = await Task(
        user_id=1, text="old", photo_file_id="old_photo"
    ).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_text)
    await state.update_data(edit_task_id=str(task.id))

    await edit_text_text(_message(uid=1, text="new text"), state)

    refreshed = await Task.get(task.id)
    assert refreshed.text == "new text"
    assert refreshed.photo_file_id is None
    assert await state.get_state() is None


async def test_edit_text_via_photo(mongo_db):
    task = await Task(user_id=1, text="old").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_text)
    await state.update_data(edit_task_id=str(task.id))
    photo = [SimpleNamespace(file_id="small"), SimpleNamespace(file_id="big")]

    await edit_text_photo(
        _message(uid=1, photo=photo, caption="new caption"), state
    )

    refreshed = await Task.get(task.id)
    assert refreshed.text == "new caption"
    assert refreshed.photo_file_id == "big"


async def test_edit_category_picked(mongo_db):
    task = await Task(user_id=1, text="chore", category="old").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_category)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "cat:kitchen")

    await edit_category_picked(callback, state)

    refreshed = await Task.get(task.id)
    assert refreshed.category == "kitchen"


async def test_edit_category_skipped_clears_it(mongo_db):
    task = await Task(user_id=1, text="chore", category="old").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_category)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "cat_skip")

    await edit_category_skipped(callback, state)

    refreshed = await Task.get(task.id)
    assert refreshed.category is None


async def test_edit_category_custom_too_long(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_category_custom)
    await state.update_data(edit_task_id=str(task.id))

    await edit_category_custom_set(_message(uid=1, text="x" * 51), state)

    assert (await Task.get(task.id)).category is None
    assert await state.get_state() == EditTask.waiting_category_custom


async def test_edit_category_custom_set(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_category_custom)
    await state.update_data(edit_task_id=str(task.id))

    await edit_category_custom_set(_message(uid=1, text="garage"), state)

    assert (await Task.get(task.id)).category == "garage"


async def test_edit_deadline_shortcut(mongo_db):
    task = await Task(
        user_id=1, text="chore", reminded=True, due_at=None
    ).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_deadline)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "due:1d")

    await edit_deadline_shortcut(callback, state)

    refreshed = await Task.get(task.id)
    assert refreshed.due_at is not None
    assert refreshed.reminded is False


async def test_edit_deadline_none_clears_repeat(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(
        user_id=1, text="chore", due_at=due, repeat_every_days=7
    ).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_deadline)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "due_none")

    await edit_deadline_none(callback, state)

    refreshed = await Task.get(task.id)
    assert refreshed.due_at is None
    assert refreshed.repeat_every_days is None


async def test_edit_deadline_manual_text(mongo_db):
    await User(user_id=1, utc_offset_minutes=0).insert()
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_deadline)
    await state.update_data(edit_task_id=str(task.id))

    await edit_deadline_text(
        _message(uid=1, text="01.01.2030 10:00"), state
    )

    refreshed = await Task.get(task.id)
    assert refreshed.due_at is not None


async def test_edit_deadline_back_returns_to_menu(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_deadline)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "nav_back")

    await edit_deadline_back(callback, state)

    assert await state.get_state() == EditTask.waiting_field


async def test_edit_repeat_none_clears_repeat_fields(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(
        user_id=1, text="chore", due_at=due, repeat_every_days=7
    ).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_repeat)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "repeat_none")

    await edit_repeat_none(callback, state)

    refreshed = await Task.get(task.id)
    assert refreshed.repeat_every_days is None
    assert refreshed.repeat_weekdays is None


async def test_edit_repeat_days_set(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="chore", due_at=due).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_repeat_days)
    await state.update_data(edit_task_id=str(task.id))

    await edit_repeat_days_set(_message(uid=1, text="5"), state)

    assert (await Task.get(task.id)).repeat_every_days == 5


async def test_edit_repeat_weekdays(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="chore", due_at=due).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_repeat_weekdays)
    await state.update_data(edit_task_id=str(task.id), selected_weekdays=[])

    await edit_repeat_weekday_toggle(_callback(1, "wd:0"), state)
    await edit_repeat_weekday_toggle(_callback(1, "wd:2"), state)
    await edit_repeat_weekdays_confirm(_callback(1, "wd_done"), state)

    refreshed = await Task.get(task.id)
    assert refreshed.repeat_weekdays == [0, 2]
    assert refreshed.repeat_every_days is None


async def test_edit_pool_picked(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_pool)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, f"task_pool:{pool.id}")

    await edit_pool_picked(callback, state)

    assert (await Task.get(task.id)).pool_id == pool.id


async def test_edit_pool_back_to_personal(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    task = await Task(user_id=1, text="chore", pool_id=pool.id).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_pool)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "task_pool:none")

    await edit_pool_picked(callback, state)

    assert (await Task.get(task.id)).pool_id is None


async def test_field_menu_blocks_pool_edit_for_non_owner(mongo_db):
    """Regression: only the owner may reassign a task's pool — a shared_with
    (non-owner, non-pool-member) editor moving it into their own pool would
    silently grant that pool's members access and could hide the task from
    its real owner."""
    owner_pool = await Pool(
        name="OwnerPool", members=[1], created_by=1
    ).insert()
    task = await Task(
        user_id=1, text="chore", pool_id=owner_pool.id, shared_with=[2]
    ).insert()
    state = await _editing(task.id, user_id=2)
    callback = _callback(2, "editf:pool")

    await cb_edit_field_picked(callback, state)

    assert await state.get_state() == EditTask.waiting_field
    callback.answer.assert_awaited_once_with(
        Messages.EDIT_POOL_OWNER_ONLY, show_alert=True
    )


async def test_edit_pool_picked_denies_non_owner_even_if_state_reached(
    mongo_db,
):
    """Defense in depth: even if waiting_pool were reached some other way,
    the terminal handler itself must still refuse a non-owner."""
    owner_pool = await Pool(
        name="OwnerPool", members=[1], created_by=1
    ).insert()
    other_pool = await Pool(
        name="Charlie's", members=[2], created_by=2
    ).insert()
    task = await Task(
        user_id=1, text="chore", pool_id=owner_pool.id, shared_with=[2]
    ).insert()
    state = _fsm(2)
    await state.set_state(EditTask.waiting_pool)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(2, f"task_pool:{other_pool.id}")

    await edit_pool_picked(callback, state)

    assert (await Task.get(task.id)).pool_id == owner_pool.id
    callback.answer.assert_awaited_once_with(
        Messages.EDIT_POOL_OWNER_ONLY, show_alert=True
    )


async def test_edit_denied_if_task_deleted_mid_flow(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_text)
    await state.update_data(edit_task_id=str(task.id))
    await task.delete()

    await edit_text_text(_message(uid=1, text="too late"), state)

    assert await state.get_state() is None


async def test_edit_callback_denied_if_task_deleted_mid_flow(mongo_db):
    task = await Task(user_id=1, text="chore", category="old").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_category)
    await state.update_data(edit_task_id=str(task.id))
    await task.delete()

    await edit_category_skipped(_callback(1, "cat_skip"), state)

    assert await state.get_state() is None


async def test_field_menu_denies_when_edit_task_id_missing(mongo_db):
    """Covers _own_task's early-return when FSM data has no edit_task_id at
    all (not just a stale/deleted one)."""
    state = _fsm(1)
    await state.set_state(EditTask.waiting_field)
    callback = _callback(1, "editf:text")

    await cb_edit_field_picked(callback, state)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )


async def test_field_menu_routes_to_category_step(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = await _editing(task.id)
    callback = _callback(1, "editf:category")

    await cb_edit_field_picked(callback, state)

    assert await state.get_state() == EditTask.waiting_category


async def test_field_menu_routes_to_deadline_step(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = await _editing(task.id)
    callback = _callback(1, "editf:deadline")

    await cb_edit_field_picked(callback, state)

    assert await state.get_state() == EditTask.waiting_deadline


async def test_field_menu_routes_to_repeat_step(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="chore", due_at=due).insert()
    state = await _editing(task.id)
    callback = _callback(1, "editf:repeat")

    await cb_edit_field_picked(callback, state)

    assert await state.get_state() == EditTask.waiting_repeat


async def test_field_menu_routes_to_pool_step_for_owner(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = await _editing(task.id)
    callback = _callback(1, "editf:pool")

    await cb_edit_field_picked(callback, state)

    assert await state.get_state() == EditTask.waiting_pool


async def test_edit_text_invalid_content_fallback(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_text)
    await state.update_data(edit_task_id=str(task.id))

    await edit_text_invalid(_message(uid=1))

    assert (await Task.get(task.id)).text == "chore"


async def test_edit_category_custom_prompt(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = await _editing(task.id)
    await state.set_state(EditTask.waiting_category)
    callback = _callback(1, "cat_custom")

    await edit_category_custom_prompt(callback, state)

    assert await state.get_state() == EditTask.waiting_category_custom


async def test_edit_category_custom_prompt_denies_stranger(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(2)
    await state.set_state(EditTask.waiting_category)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(2, "cat_custom")

    await edit_category_custom_prompt(callback, state)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )


async def test_edit_deadline_text_none(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(
        user_id=1, text="chore", due_at=due, repeat_every_days=7
    ).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_deadline)
    await state.update_data(edit_task_id=str(task.id))

    await edit_deadline_text(_message(uid=1, text="нет"), state)

    refreshed = await Task.get(task.id)
    assert refreshed.due_at is None
    assert refreshed.repeat_every_days is None


async def test_edit_deadline_text_invalid_format(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_deadline)
    await state.update_data(edit_task_id=str(task.id))

    await edit_deadline_text(_message(uid=1, text="not a date"), state)

    assert (await Task.get(task.id)).due_at is None
    assert await state.get_state() == EditTask.waiting_deadline


async def test_edit_deadline_invalid_fallback(mongo_db):
    await edit_deadline_invalid(_message(uid=1))


async def test_edit_repeat_days_prompt(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="chore", due_at=due).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_repeat)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "repeat_days")

    await edit_repeat_days_prompt(callback, state)

    assert await state.get_state() == EditTask.waiting_repeat_days


async def test_edit_repeat_days_prompt_denies_stranger(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(2)
    await state.set_state(EditTask.waiting_repeat)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(2, "repeat_days")

    await edit_repeat_days_prompt(callback, state)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )


async def test_edit_repeat_back(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="chore", due_at=due).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_repeat)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "nav_back")

    await edit_repeat_back(callback, state)

    assert await state.get_state() == EditTask.waiting_field


async def test_edit_repeat_days_set_invalid_number(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="chore", due_at=due).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_repeat_days)
    await state.update_data(edit_task_id=str(task.id))

    await edit_repeat_days_set(_message(uid=1, text="not-a-number"), state)

    assert (await Task.get(task.id)).repeat_every_days is None
    assert await state.get_state() == EditTask.waiting_repeat_days


async def test_edit_repeat_weekdays_prompt(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="chore", due_at=due).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_repeat)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "repeat_weekdays")

    await edit_repeat_weekdays_prompt(callback, state)

    assert await state.get_state() == EditTask.waiting_repeat_weekdays


async def test_edit_repeat_weekdays_prompt_denies_stranger(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(2)
    await state.set_state(EditTask.waiting_repeat)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(2, "repeat_weekdays")

    await edit_repeat_weekdays_prompt(callback, state)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )


async def test_edit_repeat_weekdays_confirm_requires_selection(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="chore", due_at=due).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_repeat_weekdays)
    await state.update_data(edit_task_id=str(task.id), selected_weekdays=[])
    callback = _callback(1, "wd_done")

    await edit_repeat_weekdays_confirm(callback, state)

    assert await state.get_state() == EditTask.waiting_repeat_weekdays
    callback.answer.assert_awaited_once_with(
        Messages.PICK_AT_LEAST_ONE_DAY, show_alert=True
    )


async def test_edit_weekdays_back(mongo_db):
    due = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = await Task(user_id=1, text="chore", due_at=due).insert()
    state = _fsm(1)
    await state.set_state(EditTask.waiting_repeat_weekdays)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(1, "nav_back")

    await edit_weekdays_back(callback, state)

    assert await state.get_state() == EditTask.waiting_repeat


async def test_edit_weekdays_back_denies_stranger(mongo_db):
    task = await Task(user_id=1, text="chore").insert()
    state = _fsm(2)
    await state.set_state(EditTask.waiting_repeat_weekdays)
    await state.update_data(edit_task_id=str(task.id))
    callback = _callback(2, "nav_back")

    await edit_weekdays_back(callback, state)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with(
        Messages.NO_ACCESS, show_alert=True
    )
