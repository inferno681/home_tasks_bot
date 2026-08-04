import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from beanie import PydanticObjectId

from bot.categories import top_categories
from bot.constants import (
    BACK_CALLBACK_DATA,
    CB_CATEGORY_CUSTOM,
    CB_CATEGORY_PREFIX,
    CB_CATEGORY_SKIP,
    CB_DUE_NONE,
    CB_DUE_PREFIX,
    CB_REPEAT_DAYS,
    CB_REPEAT_NONE,
    CB_REPEAT_WEEKDAYS,
    CB_TASK_POOL_PREFIX,
    CB_WEEKDAY_DONE,
    CB_WEEKDAY_PREFIX,
    DEADLINE_CONFIRM_LABELS,
    DEADLINE_SHORTCUTS,
    MAIN_MENU_LABELS,
    MAX_CATEGORY_BYTES,
    MENU_CANCEL,
    MENU_NEW,
    POOL_NONE,
    WEEKDAY_NAMES,
)
from bot.display import pool_label
from bot.enums import Messages
from bot.handlers.common import ensure_timezone
from bot.keyboards import (
    category_choice_kb,
    deadline_choice_kb,
    repeat_choice_kb,
    task_pool_choice_kb,
    weekday_toggle_kb,
)
from bot.models import Pool, Task, User
from bot.safe_edit import safe_delete, safe_edit_reply_markup, safe_edit_text
from bot.timeutils import to_local, to_utc, user_offset
from bot.validators import is_category_too_long

logger = logging.getLogger(__name__)

router = Router()


class NewTask(StatesGroup):
    waiting_content = State()
    waiting_pool = State()
    waiting_category = State()
    waiting_category_custom = State()
    waiting_deadline = State()
    waiting_repeat = State()
    waiting_repeat_days = State()
    waiting_repeat_weekdays = State()


@router.message(Command("new"))
@router.message(F.text == MENU_NEW)
async def cmd_new(message: Message, state: FSMContext):
    if not await ensure_timezone(message, state):
        return
    await state.set_state(NewTask.waiting_content)
    await message.answer(Messages.NEW_TASK_PROMPT)


@router.message(Command("cancel"), StateFilter("*"))
@router.message(F.text == MENU_CANCEL, StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(Messages.CANCELLED)


@router.message(NewTask.waiting_content, F.photo)
async def new_task_photo(message: Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    await state.update_data(text=message.caption, photo_file_id=photo_file_id)
    await _after_content(message, state)


@router.message(
    NewTask.waiting_content, F.text, ~F.text.in_(MAIN_MENU_LABELS)
)
async def new_task_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text, photo_file_id=None)
    await _after_content(message, state)


@router.message(NewTask.waiting_content, ~F.text.in_(MAIN_MENU_LABELS))
async def new_task_content_invalid(message: Message):
    await message.answer(Messages.INVALID_CONTENT)


async def _after_content(message: Message, state: FSMContext) -> None:
    """Either ask which pool the task goes in, or apply the silent default."""
    user = await User.find_one(User.user_id == message.from_user.id)
    if user and user.ask_pool_on_create:
        pools = await Pool.find(Pool.members == message.from_user.id).to_list()
        if pools:
            await state.set_state(NewTask.waiting_pool)
            await message.answer(
                Messages.ASK_TASK_POOL, reply_markup=task_pool_choice_kb(pools)
            )
            return
    await state.update_data(
        pool_id=user.default_pool_id if user else None
    )
    await ask_category(message, state)


@router.callback_query(
    NewTask.waiting_pool, F.data.startswith(CB_TASK_POOL_PREFIX)
)
async def pool_picked(callback: CallbackQuery, state: FSMContext):
    raw = callback.data.split(":", 1)[1]
    pool_id = None if raw == POOL_NONE else PydanticObjectId(raw)
    await state.update_data(pool_id=pool_id)
    await callback.answer()
    label = await pool_label(pool_id)
    await safe_edit_text(
        callback.message, Messages.TASK_POOL_LABEL.format(pool=label)
    )
    await ask_category(callback.message, state)


async def ask_category(message: Message, state: FSMContext) -> None:
    await state.set_state(NewTask.waiting_category)
    top = await top_categories()
    await message.answer(
        Messages.ASK_CATEGORY, reply_markup=category_choice_kb(top)
    )


@router.callback_query(
    NewTask.waiting_category, F.data.startswith(CB_CATEGORY_PREFIX)
)
async def category_picked(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    await callback.answer()
    await safe_edit_text(
        callback.message, Messages.CATEGORY_LABEL.format(category=category)
    )
    await ask_deadline(callback.message, state)


@router.callback_query(NewTask.waiting_category, F.data == CB_CATEGORY_CUSTOM)
async def category_custom_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewTask.waiting_category_custom)
    await callback.answer()
    await safe_edit_text(callback.message, Messages.CATEGORY_CUSTOM_WAITING)
    await callback.message.answer(Messages.CATEGORY_CUSTOM_PROMPT)


@router.callback_query(NewTask.waiting_category, F.data == CB_CATEGORY_SKIP)
async def category_skipped(callback: CallbackQuery, state: FSMContext):
    await state.update_data(category=None)
    await callback.answer()
    await safe_edit_text(callback.message, Messages.CATEGORY_NONE)
    await ask_deadline(callback.message, state)


@router.message(
    NewTask.waiting_category_custom, F.text, ~F.text.in_(MAIN_MENU_LABELS)
)
async def category_custom_set(message: Message, state: FSMContext):
    category = message.text.strip()
    if is_category_too_long(category):
        await message.answer(
            Messages.CATEGORY_TOO_LONG.format(limit=MAX_CATEGORY_BYTES)
        )
        return
    await state.update_data(category=category)
    await ask_deadline(message, state)


async def ask_deadline(message: Message, state: FSMContext) -> None:
    await state.set_state(NewTask.waiting_deadline)
    await message.answer(
        Messages.ASK_DEADLINE, reply_markup=deadline_choice_kb()
    )


@router.callback_query(
    NewTask.waiting_deadline, F.data.startswith(CB_DUE_PREFIX)
)
async def deadline_shortcut(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    delta = DEADLINE_SHORTCUTS[key]
    await callback.answer()
    await state.update_data(due_at=datetime.now(timezone.utc) + delta)
    await safe_edit_text(
        callback.message,
        Messages.DEADLINE_LABEL.format(label=DEADLINE_CONFIRM_LABELS[key]),
    )
    await ask_repeat(callback.message, state)


@router.callback_query(NewTask.waiting_deadline, F.data == CB_DUE_NONE)
async def deadline_none(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(due_at=None)
    await safe_edit_text(callback.message, Messages.DEADLINE_NONE)
    task = await _create_task(callback.from_user.id, state)
    await callback.message.answer(
        await _confirmation_text(task, callback.from_user.id)
    )


@router.callback_query(NewTask.waiting_deadline, F.data == BACK_CALLBACK_DATA)
async def deadline_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await safe_delete(callback.message)
    await ask_category(callback.message, state)


@router.message(
    NewTask.waiting_deadline, F.text, ~F.text.in_(MAIN_MENU_LABELS)
)
async def new_task_deadline(message: Message, state: FSMContext):
    if message.text.strip().lower() in ("нет", "no", "-"):
        await state.update_data(due_at=None)
        task = await _create_task(message.from_user.id, state)
        await message.answer(
            await _confirmation_text(task, message.from_user.id)
        )
        return

    try:
        local_dt = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer(Messages.INVALID_DATE)
        return

    user = await User.find_one(User.user_id == message.from_user.id)
    offset = user_offset(user.utc_offset_minutes if user else None)
    await state.update_data(due_at=to_utc(local_dt, offset))
    await ask_repeat(message, state)


@router.message(NewTask.waiting_deadline, ~F.text.in_(MAIN_MENU_LABELS))
async def new_task_deadline_invalid(message: Message):
    await message.answer(Messages.DEADLINE_TEXT_HINT)


async def ask_repeat(message: Message, state: FSMContext) -> None:
    await state.set_state(NewTask.waiting_repeat)
    await message.answer(Messages.ASK_REPEAT, reply_markup=repeat_choice_kb())


@router.callback_query(NewTask.waiting_repeat, F.data == CB_REPEAT_NONE)
async def repeat_none(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await safe_edit_text(callback.message, Messages.REPEAT_NONE)
    task = await _create_task(callback.from_user.id, state)
    await callback.message.answer(
        await _confirmation_text(task, callback.from_user.id)
    )


@router.callback_query(NewTask.waiting_repeat, F.data == CB_REPEAT_DAYS)
async def repeat_days_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewTask.waiting_repeat_days)
    await callback.answer()
    await safe_edit_text(callback.message, Messages.REPEAT_DAYS_WAITING)
    await callback.message.answer(Messages.ASK_REPEAT_DAYS)


@router.callback_query(NewTask.waiting_repeat, F.data == BACK_CALLBACK_DATA)
async def repeat_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await safe_delete(callback.message)
    await ask_deadline(callback.message, state)


@router.message(
    NewTask.waiting_repeat_days, F.text, ~F.text.in_(MAIN_MENU_LABELS)
)
async def repeat_days_set(message: Message, state: FSMContext):
    raw = message.text.strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(Messages.INVALID_REPEAT_DAYS)
        return
    await state.update_data(repeat_every_days=int(raw))
    task = await _create_task(message.from_user.id, state)
    await message.answer(
        await _confirmation_text(task, message.from_user.id)
    )


@router.callback_query(NewTask.waiting_repeat, F.data == CB_REPEAT_WEEKDAYS)
async def repeat_weekdays_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewTask.waiting_repeat_weekdays)
    await state.update_data(selected_weekdays=[])
    await callback.answer()
    await safe_edit_text(callback.message, Messages.REPEAT_WEEKDAYS_WAITING)
    await callback.message.answer(
        Messages.ASK_WEEKDAYS, reply_markup=weekday_toggle_kb([])
    )


@router.callback_query(
    NewTask.waiting_repeat_weekdays, F.data.startswith(CB_WEEKDAY_PREFIX)
)
async def repeat_weekday_toggle(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    selected = set(data.get("selected_weekdays", []))
    selected.symmetric_difference_update({idx})
    await state.update_data(selected_weekdays=sorted(selected))
    await callback.answer()
    await safe_edit_reply_markup(
        callback.message, weekday_toggle_kb(selected)
    )


@router.callback_query(
    NewTask.waiting_repeat_weekdays, F.data == CB_WEEKDAY_DONE
)
async def repeat_weekdays_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_weekdays", [])
    if not selected:
        await callback.answer(Messages.PICK_AT_LEAST_ONE_DAY, show_alert=True)
        return
    await callback.answer()
    await state.update_data(repeat_weekdays=selected)
    days = ", ".join(WEEKDAY_NAMES[i] for i in selected)
    await safe_edit_text(
        callback.message, Messages.REPEAT_WEEKDAYS_LABEL.format(days=days)
    )
    task = await _create_task(callback.from_user.id, state)
    await callback.message.answer(
        await _confirmation_text(task, callback.from_user.id)
    )


@router.callback_query(
    NewTask.waiting_repeat_weekdays, F.data == BACK_CALLBACK_DATA
)
async def weekdays_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await safe_delete(callback.message)
    await ask_repeat(callback.message, state)


async def _create_task(user_id: int, state: FSMContext) -> Task:
    data = await state.get_data()
    task = Task(
        user_id=user_id,
        text=data.get("text"),
        photo_file_id=data.get("photo_file_id"),
        due_at=data.get("due_at"),
        category=data.get("category"),
        pool_id=data.get("pool_id"),
        repeat_every_days=data.get("repeat_every_days"),
        repeat_weekdays=data.get("repeat_weekdays") or None,
    )
    await task.insert()
    await state.clear()
    logger.info(f"Task {task.id} created by user {user_id}")
    return task


async def _confirmation_text(task: Task, user_id: int) -> str:
    parts = [Messages.TASK_SAVED]
    if task.due_at:
        user = await User.find_one(User.user_id == user_id)
        offset = user_offset(user.utc_offset_minutes if user else None)
        local_due = to_local(task.due_at, offset)
        when = local_due.strftime("%d.%m.%Y %H:%M")
        parts.append(Messages.REMINDER_LINE.format(when=when))
    if task.pool_id:
        pool = await Pool.get(task.pool_id)
        if pool:
            parts.append(Messages.TASK_POOL_LABEL.format(pool=pool.name))
    if task.category:
        parts.append(Messages.CATEGORY_LINE.format(category=task.category))
    if task.repeat_every_days:
        parts.append(
            Messages.REPEAT_DAYS_LINE.format(days=task.repeat_every_days)
        )
    if task.repeat_weekdays:
        days = ", ".join(WEEKDAY_NAMES[i] for i in task.repeat_weekdays)
        parts.append(Messages.REPEAT_WEEKDAYS_LINE.format(days=days))
    return " ".join(parts)
