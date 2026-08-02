import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.categories import top_categories
from bot.handlers.common import ensure_timezone
from bot.keyboards import (
    category_choice_kb,
    deadline_choice_kb,
    repeat_choice_kb,
    weekday_toggle_kb,
)
from bot.models import Task, User
from bot.timeutils import to_local, to_utc, user_offset

logger = logging.getLogger(__name__)

router = Router()

DEADLINE_SHORTCUTS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
    "1mo": timedelta(days=30),  # ponytail: приближение, не календарный месяц
}


class NewTask(StatesGroup):
    waiting_content = State()
    waiting_category = State()
    waiting_category_custom = State()
    waiting_deadline = State()
    waiting_repeat = State()
    waiting_repeat_days = State()
    waiting_repeat_weekdays = State()


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext):
    if not await ensure_timezone(message, state):
        return
    await state.set_state(NewTask.waiting_content)
    await message.answer(
        "Пришли текст, фото или фото с подписью для новой задачи.\n"
        "Можно отменить командой /cancel."
    )


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


@router.message(NewTask.waiting_content, F.photo)
async def new_task_photo(message: Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    await state.update_data(text=message.caption, photo_file_id=photo_file_id)
    await ask_category(message, state)


@router.message(NewTask.waiting_content, F.text)
async def new_task_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text, photo_file_id=None)
    await ask_category(message, state)


@router.message(NewTask.waiting_content)
async def new_task_content_invalid(message: Message):
    await message.answer("Пришли текст, фото или фото с подписью.")


async def ask_category(message: Message, state: FSMContext) -> None:
    await state.set_state(NewTask.waiting_category)
    top = await top_categories()
    await message.answer(
        "Есть категория? Выбери или добавь свою.",
        reply_markup=category_choice_kb(top),
    )


@router.callback_query(NewTask.waiting_category, F.data.startswith("cat:"))
async def category_picked(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    await callback.answer()
    await ask_deadline(callback.message, state)


@router.callback_query(NewTask.waiting_category, F.data == "cat_custom")
async def category_custom_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewTask.waiting_category_custom)
    await callback.answer()
    await callback.message.answer("Впиши название категории.")


@router.callback_query(NewTask.waiting_category, F.data == "cat_skip")
async def category_skipped(callback: CallbackQuery, state: FSMContext):
    await state.update_data(category=None)
    await callback.answer()
    await ask_deadline(callback.message, state)


@router.message(NewTask.waiting_category_custom, F.text)
async def category_custom_set(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await ask_deadline(message, state)


async def ask_deadline(message: Message, state: FSMContext) -> None:
    await state.set_state(NewTask.waiting_deadline)
    await message.answer(
        "Есть срок? Выбери готовый вариант, пришли дату и время в формате "
        "ДД.ММ.ГГГГ ЧЧ:ММ, или напиши 'нет'.",
        reply_markup=deadline_choice_kb(),
    )


@router.callback_query(NewTask.waiting_deadline, F.data.startswith("due:"))
async def deadline_shortcut(callback: CallbackQuery, state: FSMContext):
    delta = DEADLINE_SHORTCUTS[callback.data.split(":", 1)[1]]
    await callback.answer()
    await state.update_data(due_at=datetime.now(timezone.utc) + delta)
    await ask_repeat(callback.message, state)


@router.callback_query(NewTask.waiting_deadline, F.data == "due_none")
async def deadline_none(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(due_at=None)
    task = await _create_task(callback.from_user.id, state)
    await callback.message.answer(
        await _confirmation_text(task, callback.from_user.id)
    )


@router.message(NewTask.waiting_deadline, F.text)
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
        await message.answer(
            "Не понял дату. Формат: ДД.ММ.ГГГГ ЧЧ:ММ, или 'нет'."
        )
        return

    user = await User.find_one(User.user_id == message.from_user.id)
    await state.update_data(due_at=to_utc(local_dt, user_offset(user)))
    await ask_repeat(message, state)


@router.message(NewTask.waiting_deadline)
async def new_task_deadline_invalid(message: Message):
    await message.answer(
        "Пришли дату текстом в формате ДД.ММ.ГГГГ ЧЧ:ММ, или 'нет'."
    )


async def ask_repeat(message: Message, state: FSMContext) -> None:
    await state.set_state(NewTask.waiting_repeat)
    await message.answer("Повторять задачу?", reply_markup=repeat_choice_kb())


@router.callback_query(NewTask.waiting_repeat, F.data == "repeat_none")
async def repeat_none(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task = await _create_task(callback.from_user.id, state)
    await callback.message.answer(
        await _confirmation_text(task, callback.from_user.id)
    )


@router.callback_query(NewTask.waiting_repeat, F.data == "repeat_days")
async def repeat_days_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewTask.waiting_repeat_days)
    await callback.answer()
    await callback.message.answer(
        "Через сколько дней повторять? Пришли число."
    )


@router.message(NewTask.waiting_repeat_days, F.text)
async def repeat_days_set(message: Message, state: FSMContext):
    raw = message.text.strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Пришли положительное целое число дней.")
        return
    await state.update_data(repeat_every_days=int(raw))
    task = await _create_task(message.from_user.id, state)
    await message.answer(
        await _confirmation_text(task, message.from_user.id)
    )


@router.callback_query(NewTask.waiting_repeat, F.data == "repeat_weekdays")
async def repeat_weekdays_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewTask.waiting_repeat_weekdays)
    await state.update_data(selected_weekdays=[])
    await callback.answer()
    await callback.message.answer(
        "Выбери дни недели, потом нажми «Готово».",
        reply_markup=weekday_toggle_kb([]),
    )


@router.callback_query(
    NewTask.waiting_repeat_weekdays, F.data.startswith("wd:")
)
async def repeat_weekday_toggle(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    selected = set(data.get("selected_weekdays", []))
    selected.symmetric_difference_update({idx})
    await state.update_data(selected_weekdays=sorted(selected))
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=weekday_toggle_kb(selected)
    )


@router.callback_query(NewTask.waiting_repeat_weekdays, F.data == "wd_done")
async def repeat_weekdays_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_weekdays", [])
    if not selected:
        await callback.answer("Выбери хотя бы один день.", show_alert=True)
        return
    await callback.answer()
    await state.update_data(repeat_weekdays=selected)
    task = await _create_task(callback.from_user.id, state)
    await callback.message.answer(
        await _confirmation_text(task, callback.from_user.id)
    )


async def _create_task(user_id: int, state: FSMContext) -> Task:
    data = await state.get_data()
    task = Task(
        user_id=user_id,
        text=data.get("text"),
        photo_file_id=data.get("photo_file_id"),
        due_at=data.get("due_at"),
        category=data.get("category"),
        repeat_every_days=data.get("repeat_every_days"),
        repeat_weekdays=data.get("repeat_weekdays") or None,
    )
    await task.insert()
    await state.clear()
    logger.info(f"Task {task.id} created by user {user_id}")
    return task


async def _confirmation_text(task: Task, user_id: int) -> str:
    parts = ["Задача сохранена."]
    if task.due_at:
        user = await User.find_one(User.user_id == user_id)
        local_due = to_local(task.due_at, user_offset(user))
        parts.append(f"Напомню {local_due.strftime('%d.%m.%Y %H:%M')}.")
    if task.category:
        parts.append(f"Категория: {task.category}.")
    if task.repeat_every_days:
        parts.append(f"Повтор: каждые {task.repeat_every_days} дн.")
    if task.repeat_weekdays:
        names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        days = ", ".join(names[i] for i in task.repeat_weekdays)
        parts.append(f"Повтор по дням: {days}.")
    return " ".join(parts)
