import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from beanie import PydanticObjectId
from beanie.operators import Set

from bot.categories import top_categories
from bot.constants import (
    BACK_CALLBACK_DATA,
    CB_CATEGORY_CUSTOM,
    CB_CATEGORY_PREFIX,
    CB_CATEGORY_SKIP,
    CB_DUE_NONE,
    CB_DUE_PREFIX,
    CB_EDIT_CANCEL,
    CB_EDIT_FIELD_PREFIX,
    CB_REPEAT_DAYS,
    CB_REPEAT_NONE,
    CB_REPEAT_WEEKDAYS,
    CB_TASK_EDIT_PREFIX,
    CB_TASK_POOL_PREFIX,
    CB_WEEKDAY_DONE,
    CB_WEEKDAY_PREFIX,
    DEADLINE_CONFIRM_LABELS,
    DEADLINE_SHORTCUTS,
    EDIT_FIELD_CATEGORY,
    EDIT_FIELD_DEADLINE,
    EDIT_FIELD_POOL,
    EDIT_FIELD_REPEAT,
    EDIT_FIELD_TEXT,
    MAIN_MENU_LABELS,
    MAX_CATEGORY_BYTES,
    POOL_NONE,
    WEEKDAY_NAMES,
)
from bot.display import pool_label
from bot.enums import Messages
from bot.keyboards import (
    category_choice_kb,
    deadline_choice_kb,
    edit_menu_kb,
    repeat_choice_kb,
    task_pool_choice_kb,
    weekday_toggle_kb,
)
from bot.models import Pool, Task, User
from bot.safe_edit import safe_edit_reply_markup, safe_edit_text
from bot.task_access import get_task, is_task_authorized
from bot.timeutils import to_utc, user_offset
from bot.validators import is_category_too_long

logger = logging.getLogger(__name__)

router = Router()


class EditTask(StatesGroup):
    waiting_field = State()
    waiting_text = State()
    waiting_category = State()
    waiting_category_custom = State()
    waiting_deadline = State()
    waiting_repeat = State()
    waiting_repeat_days = State()
    waiting_repeat_weekdays = State()
    waiting_pool = State()


async def _own_task(state: FSMContext, uid: int) -> Optional[Task]:
    """Re-fetch the task being edited and re-check authorization.

    The task_id lives in FSM state (set once in cb_edit_start), not in each
    step's callback_data — this just guards against the task having been
    deleted or access revoked mid-edit, not against tampering (FSM state
    isn't client-suppliable the way callback_data/deep-link payloads are).
    """
    data = await state.get_data()
    task_id = data.get("edit_task_id")
    if not task_id:
        return None
    task = await get_task(task_id)
    if not task or not await is_task_authorized(task, uid):
        return None
    return task


async def _finish_callback_edit(
    callback: CallbackQuery, state: FSMContext, update_op, confirmation: str
) -> None:
    task = await _own_task(state, callback.from_user.id)
    if not task:
        await callback.answer(Messages.NO_ACCESS, show_alert=True)
        await state.clear()
        return
    await task.update(update_op)
    await state.clear()
    logger.info(f"Task {task.id} edited by {callback.from_user.id}")
    await callback.answer()
    await safe_edit_text(callback.message, confirmation)


async def _finish_message_edit(
    message: Message, state: FSMContext, update_op, confirmation: str
) -> None:
    task = await _own_task(state, message.from_user.id)
    if not task:
        await message.answer(Messages.NO_ACCESS)
        await state.clear()
        return
    await task.update(update_op)
    await state.clear()
    logger.info(f"Task {task.id} edited by {message.from_user.id}")
    await message.answer(confirmation)


@router.callback_query(F.data.startswith(CB_TASK_EDIT_PREFIX))
async def cb_edit_start(callback: CallbackQuery, state: FSMContext):
    task_id = callback.data.split(":", 1)[1]
    task = await get_task(task_id)
    uid = callback.from_user.id
    if not task or not await is_task_authorized(task, uid):
        await callback.answer(Messages.NO_ACCESS, show_alert=True)
        return

    await state.set_state(EditTask.waiting_field)
    await state.update_data(edit_task_id=task_id)
    await callback.answer()
    await callback.message.answer(
        Messages.EDIT_MENU_TITLE, reply_markup=edit_menu_kb()
    )


@router.callback_query(EditTask.waiting_field, F.data == CB_EDIT_CANCEL)
async def cb_edit_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await safe_edit_text(callback.message, Messages.CANCELLED)


@router.callback_query(
    EditTask.waiting_field, F.data.startswith(CB_EDIT_FIELD_PREFIX)
)
async def _show_text_step(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditTask.waiting_text)
    await safe_edit_text(callback.message, Messages.EDIT_TEXT_PROMPT)


async def _show_category_step(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.set_state(EditTask.waiting_category)
    top = await top_categories()
    await safe_edit_text(
        callback.message, Messages.ASK_CATEGORY, markup=category_choice_kb(top)
    )


async def _show_deadline_step(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.set_state(EditTask.waiting_deadline)
    await safe_edit_text(
        callback.message, Messages.ASK_DEADLINE, markup=deadline_choice_kb()
    )


async def _show_repeat_step(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.set_state(EditTask.waiting_repeat)
    await safe_edit_text(
        callback.message, Messages.ASK_REPEAT, markup=repeat_choice_kb()
    )


async def _show_pool_step(callback: CallbackQuery, state: FSMContext) -> None:
    pools = await Pool.find(Pool.members == callback.from_user.id).to_list()
    await state.set_state(EditTask.waiting_pool)
    await safe_edit_text(
        callback.message,
        Messages.ASK_TASK_POOL,
        markup=task_pool_choice_kb(pools),
    )


_FIELD_STEPS = {
    EDIT_FIELD_TEXT: _show_text_step,
    EDIT_FIELD_CATEGORY: _show_category_step,
    EDIT_FIELD_DEADLINE: _show_deadline_step,
    EDIT_FIELD_REPEAT: _show_repeat_step,
    EDIT_FIELD_POOL: _show_pool_step,
}


async def cb_edit_field_picked(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    task = await _own_task(state, callback.from_user.id)
    if not task:
        await callback.answer(Messages.NO_ACCESS, show_alert=True)
        await state.clear()
        return

    if field == EDIT_FIELD_REPEAT and not task.due_at:
        await callback.answer(Messages.EDIT_NEEDS_DEADLINE, show_alert=True)
        return

    await callback.answer()
    await _FIELD_STEPS[field](callback, state)


async def _back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditTask.waiting_field)
    await callback.answer()
    await safe_edit_text(
        callback.message, Messages.EDIT_MENU_TITLE, markup=edit_menu_kb()
    )


# --- Текст/фото ---


@router.message(EditTask.waiting_text, F.photo)
async def edit_text_photo(message: Message, state: FSMContext):
    await _finish_message_edit(
        message,
        state,
        Set(
            {
                Task.text: message.caption,
                Task.photo_file_id: message.photo[-1].file_id,
            }
        ),
        Messages.TASK_TEXT_UPDATED,
    )


@router.message(EditTask.waiting_text, F.text, ~F.text.in_(MAIN_MENU_LABELS))
async def edit_text_text(message: Message, state: FSMContext):
    await _finish_message_edit(
        message,
        state,
        Set({Task.text: message.text, Task.photo_file_id: None}),
        Messages.TASK_TEXT_UPDATED,
    )


@router.message(EditTask.waiting_text, ~F.text.in_(MAIN_MENU_LABELS))
async def edit_text_invalid(message: Message):
    await message.answer(Messages.INVALID_CONTENT)


# --- Категория ---


@router.callback_query(
    EditTask.waiting_category, F.data.startswith(CB_CATEGORY_PREFIX)
)
async def edit_category_picked(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await _finish_callback_edit(
        callback,
        state,
        Set({Task.category: category}),
        Messages.CATEGORY_LABEL.format(category=category),
    )


@router.callback_query(EditTask.waiting_category, F.data == CB_CATEGORY_CUSTOM)
async def edit_category_custom_prompt(
    callback: CallbackQuery, state: FSMContext
):
    task = await _own_task(state, callback.from_user.id)
    if not task:
        await callback.answer(Messages.NO_ACCESS, show_alert=True)
        await state.clear()
        return
    await state.set_state(EditTask.waiting_category_custom)
    await callback.answer()
    await safe_edit_text(callback.message, Messages.CATEGORY_CUSTOM_PROMPT)


@router.callback_query(EditTask.waiting_category, F.data == CB_CATEGORY_SKIP)
async def edit_category_skipped(callback: CallbackQuery, state: FSMContext):
    await _finish_callback_edit(
        callback, state, Set({Task.category: None}), Messages.CATEGORY_NONE
    )


@router.message(
    EditTask.waiting_category_custom, F.text, ~F.text.in_(MAIN_MENU_LABELS)
)
async def edit_category_custom_set(message: Message, state: FSMContext):
    category = message.text.strip()
    if is_category_too_long(category):
        await message.answer(
            Messages.CATEGORY_TOO_LONG.format(limit=MAX_CATEGORY_BYTES)
        )
        return
    await _finish_message_edit(
        message,
        state,
        Set({Task.category: category}),
        Messages.CATEGORY_LABEL.format(category=category),
    )


# --- Срок ---


@router.callback_query(
    EditTask.waiting_deadline, F.data.startswith(CB_DUE_PREFIX)
)
async def edit_deadline_shortcut(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    new_due = datetime.now(timezone.utc) + DEADLINE_SHORTCUTS[key]
    await _finish_callback_edit(
        callback,
        state,
        Set({Task.due_at: new_due, Task.reminded: False}),
        Messages.DEADLINE_LABEL.format(label=DEADLINE_CONFIRM_LABELS[key]),
    )


@router.callback_query(EditTask.waiting_deadline, F.data == CB_DUE_NONE)
async def edit_deadline_none(callback: CallbackQuery, state: FSMContext):
    await _finish_callback_edit(
        callback,
        state,
        Set(
            {
                Task.due_at: None,
                Task.reminded: False,
                Task.repeat_every_days: None,
                Task.repeat_weekdays: None,
            }
        ),
        Messages.DEADLINE_NONE,
    )


@router.callback_query(EditTask.waiting_deadline, F.data == BACK_CALLBACK_DATA)
async def edit_deadline_back(callback: CallbackQuery, state: FSMContext):
    await _back_to_menu(callback, state)


@router.message(
    EditTask.waiting_deadline, F.text, ~F.text.in_(MAIN_MENU_LABELS)
)
async def edit_deadline_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() in ("нет", "no", "-"):
        await _finish_message_edit(
            message,
            state,
            Set(
                {
                    Task.due_at: None,
                    Task.reminded: False,
                    Task.repeat_every_days: None,
                    Task.repeat_weekdays: None,
                }
            ),
            Messages.DEADLINE_NONE,
        )
        return

    try:
        local_dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer(Messages.INVALID_DATE)
        return

    user = await User.find_one(User.user_id == message.from_user.id)
    offset = user_offset(user.utc_offset_minutes if user else None)
    when = local_dt.strftime("%d.%m.%Y %H:%M")
    await _finish_message_edit(
        message,
        state,
        Set({Task.due_at: to_utc(local_dt, offset), Task.reminded: False}),
        Messages.DEADLINE_LABEL.format(label=when),
    )


@router.message(EditTask.waiting_deadline, ~F.text.in_(MAIN_MENU_LABELS))
async def edit_deadline_invalid(message: Message):
    await message.answer(Messages.DEADLINE_TEXT_HINT)


# --- Повтор ---


@router.callback_query(EditTask.waiting_repeat, F.data == CB_REPEAT_NONE)
async def edit_repeat_none(callback: CallbackQuery, state: FSMContext):
    await _finish_callback_edit(
        callback,
        state,
        Set({Task.repeat_every_days: None, Task.repeat_weekdays: None}),
        Messages.REPEAT_NONE,
    )


@router.callback_query(EditTask.waiting_repeat, F.data == CB_REPEAT_DAYS)
async def edit_repeat_days_prompt(callback: CallbackQuery, state: FSMContext):
    task = await _own_task(state, callback.from_user.id)
    if not task:
        await callback.answer(Messages.NO_ACCESS, show_alert=True)
        await state.clear()
        return
    await state.set_state(EditTask.waiting_repeat_days)
    await callback.answer()
    await safe_edit_text(callback.message, Messages.REPEAT_DAYS_WAITING)
    await callback.message.answer(Messages.ASK_REPEAT_DAYS)


@router.callback_query(EditTask.waiting_repeat, F.data == BACK_CALLBACK_DATA)
async def edit_repeat_back(callback: CallbackQuery, state: FSMContext):
    await _back_to_menu(callback, state)


@router.message(
    EditTask.waiting_repeat_days, F.text, ~F.text.in_(MAIN_MENU_LABELS)
)
async def edit_repeat_days_set(message: Message, state: FSMContext):
    raw = message.text.strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(Messages.INVALID_REPEAT_DAYS)
        return
    await _finish_message_edit(
        message,
        state,
        Set({Task.repeat_every_days: int(raw), Task.repeat_weekdays: None}),
        Messages.REPEAT_DAYS_LINE.format(days=int(raw)),
    )


@router.callback_query(EditTask.waiting_repeat, F.data == CB_REPEAT_WEEKDAYS)
async def edit_repeat_weekdays_prompt(
    callback: CallbackQuery, state: FSMContext
):
    task = await _own_task(state, callback.from_user.id)
    if not task:
        await callback.answer(Messages.NO_ACCESS, show_alert=True)
        await state.clear()
        return
    await state.set_state(EditTask.waiting_repeat_weekdays)
    await state.update_data(selected_weekdays=[])
    await callback.answer()
    await safe_edit_text(callback.message, Messages.REPEAT_WEEKDAYS_WAITING)
    await callback.message.answer(
        Messages.ASK_WEEKDAYS, reply_markup=weekday_toggle_kb([])
    )


@router.callback_query(
    EditTask.waiting_repeat_weekdays, F.data.startswith(CB_WEEKDAY_PREFIX)
)
async def edit_repeat_weekday_toggle(
    callback: CallbackQuery, state: FSMContext
):
    idx = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    selected = set(data.get("selected_weekdays", []))
    selected.symmetric_difference_update({idx})
    await state.update_data(selected_weekdays=sorted(selected))
    await callback.answer()
    await safe_edit_reply_markup(callback.message, weekday_toggle_kb(selected))


@router.callback_query(
    EditTask.waiting_repeat_weekdays, F.data == CB_WEEKDAY_DONE
)
async def edit_repeat_weekdays_confirm(
    callback: CallbackQuery, state: FSMContext
):
    data = await state.get_data()
    selected = data.get("selected_weekdays", [])
    if not selected:
        await callback.answer(Messages.PICK_AT_LEAST_ONE_DAY, show_alert=True)
        return
    days = ", ".join(WEEKDAY_NAMES[i] for i in selected)
    await _finish_callback_edit(
        callback,
        state,
        Set({Task.repeat_weekdays: selected, Task.repeat_every_days: None}),
        Messages.REPEAT_WEEKDAYS_LABEL.format(days=days),
    )


@router.callback_query(
    EditTask.waiting_repeat_weekdays, F.data == BACK_CALLBACK_DATA
)
async def edit_weekdays_back(callback: CallbackQuery, state: FSMContext):
    task = await _own_task(state, callback.from_user.id)
    if not task:
        await callback.answer(Messages.NO_ACCESS, show_alert=True)
        await state.clear()
        return
    await state.set_state(EditTask.waiting_repeat)
    await callback.answer()
    await safe_edit_text(
        callback.message, Messages.ASK_REPEAT, markup=repeat_choice_kb()
    )


# --- Пул ---


@router.callback_query(
    EditTask.waiting_pool, F.data.startswith(CB_TASK_POOL_PREFIX)
)
async def edit_pool_picked(callback: CallbackQuery, state: FSMContext):
    raw = callback.data.split(":", 1)[1]
    pool_id = None if raw == POOL_NONE else PydanticObjectId(raw)
    label = await pool_label(pool_id)
    await _finish_callback_edit(
        callback,
        state,
        Set({Task.pool_id: pool_id}),
        Messages.TASK_POOL_LABEL.format(pool=label),
    )
