import logging
from datetime import datetime, timezone
from typing import List, Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from beanie import PydanticObjectId
from beanie.operators import AddToSet, Or, Set
from bson.errors import InvalidId

from bot.handlers.common import ensure_timezone
from bot.keyboards import WEEKDAY_NAMES, task_actions_kb
from bot.models import Task, TaskStatus, User
from bot.recurrence import next_due_date
from bot.timeutils import to_local, user_offset

logger = logging.getLogger(__name__)

router = Router()


async def _open_tasks_for(
    uid: int, category: Optional[str] = None
) -> List[Task]:
    conditions = [
        Or(Task.user_id == uid, Task.shared_with == uid),
        Task.status == TaskStatus.PENDING,
    ]
    if category:
        conditions.append(Task.category == category)
    return await Task.find(*conditions).sort("+due_at").to_list()


async def _get_task(task_id: str) -> Optional[Task]:
    try:
        object_id = PydanticObjectId(task_id)
    except InvalidId:
        return None
    return await Task.get(object_id)


def _authorized(task: Task, uid: int) -> bool:
    return task.user_id == uid or uid in task.shared_with


async def _caption(task: Task, offset: int) -> str:
    lines = [task.text or "(без текста)", f"id: {task.id}"]
    if task.category:
        lines.append(f"🏷 {task.category}")
    if task.due_at:
        local_due = to_local(task.due_at, offset)
        lines.append(f"⏰ {local_due.strftime('%d.%m.%Y %H:%M')}")
    if task.assigned_to:
        assignee = await User.find_one(User.user_id == task.assigned_to)
        if assignee and assignee.username:
            lines.append(f"👤 @{assignee.username}")
    if task.repeat_every_days:
        lines.append(f"🔁 каждые {task.repeat_every_days} дн.")
    if task.repeat_weekdays:
        days = ", ".join(WEEKDAY_NAMES[i] for i in task.repeat_weekdays)
        lines.append(f"🔁 по дням: {days}")
    if task.completed_history:
        last = to_local(task.completed_history[-1], offset)
        lines.append(f"✅ последний раз: {last.strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(lines)


@router.message(Command("list"))
async def cmd_list(
    message: Message, state: FSMContext, command: CommandObject
):
    if not await ensure_timezone(message, state):
        return

    uid = message.from_user.id
    category = (command.args or "").strip() or None
    tasks = await _open_tasks_for(uid, category)

    if not tasks:
        await message.answer("Открытых задач нет.")
        return

    user = await User.find_one(User.user_id == uid)
    offset = user_offset(user)

    for task in tasks:
        caption = await _caption(task, offset)
        kb = task_actions_kb(str(task.id))
        if task.photo_file_id:
            await message.answer_photo(
                task.photo_file_id, caption=caption, reply_markup=kb
            )
        else:
            await message.answer(caption, reply_markup=kb)


@router.message(Command("share"))
async def cmd_share(message: Message, command: CommandObject):
    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2:
        await message.answer("Формат: /share <id задачи из /list> <@username>")
        return

    task_id, username = args[0], args[1].lstrip("@")
    uid = message.from_user.id

    task = await _get_task(task_id)
    if not task:
        await message.answer("Нет задачи с таким id. Посмотри /list.")
        return
    if task.user_id != uid:
        await message.answer("Делиться можно только своими задачами.")
        return

    target = await User.find_one(User.username == username)
    if not target:
        await message.answer(
            "Этот пользователь ещё не писал боту — "
            "пусть сначала отправит /start."
        )
        return
    if target.user_id == uid or target.user_id in task.shared_with:
        await message.answer("Уже расшарено.")
        return

    await task.update(AddToSet({Task.shared_with: target.user_id}))
    logger.info(f"Task {task.id} shared by {uid} with @{username}")
    await message.answer(f"Задача расшарена с @{username}.")


@router.message(Command("assign"))
async def cmd_assign(message: Message, command: CommandObject):
    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2:
        await message.answer(
            "Формат: /assign <id задачи из /list> <@username>"
        )
        return

    task_id, username = args[0], args[1].lstrip("@")
    uid = message.from_user.id

    task = await _get_task(task_id)
    if not task:
        await message.answer("Нет задачи с таким id. Посмотри /list.")
        return
    if task.user_id != uid:
        await message.answer("Назначать можно только на своих задачах.")
        return

    target = await User.find_one(User.username == username)
    if not target:
        await message.answer(
            "Этот пользователь ещё не писал боту — "
            "пусть сначала отправит /start."
        )
        return

    await task.update(
        Set({Task.assigned_to: target.user_id}),
        AddToSet({Task.shared_with: target.user_id}),
    )
    logger.info(f"Task {task.id} assigned by {uid} to @{username}")
    await message.answer(f"Задача назначена на @{username}.")


def _log_denied(task: Optional[Task], uid: int, action: str) -> None:
    if task is not None:
        logger.warning(f"User {uid} denied {action} on task {task.id}")


@router.callback_query(F.data.startswith("done:"))
async def cb_done(callback: CallbackQuery):
    task_id = callback.data.split(":", 1)[1]
    task = await _get_task(task_id)
    uid = callback.from_user.id
    if not task or not _authorized(task, uid):
        _log_denied(task, uid, "done")
        await callback.answer("Нет доступа к этой задаче.", show_alert=True)
        return

    if task.due_at and (task.repeat_every_days or task.repeat_weekdays):
        new_due = next_due_date(
            task.due_at, task.repeat_every_days, task.repeat_weekdays
        )
        await task.update(
            Set({Task.due_at: new_due, Task.reminded: False}),
            AddToSet({Task.completed_history: datetime.now(timezone.utc)}),
        )
        logger.info(f"Task {task.id} completed by {uid}, rescheduled")
        await callback.answer("Сделано! Повторю в следующий раз ✅")
        return

    task.status = TaskStatus.DONE
    await task.save()
    logger.info(f"Task {task.id} marked done by {uid}")
    await callback.answer("Отмечено как сделано ✅")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("delete:"))
async def cb_delete(callback: CallbackQuery):
    task_id = callback.data.split(":", 1)[1]
    task = await _get_task(task_id)
    uid = callback.from_user.id
    if not task or not _authorized(task, uid):
        _log_denied(task, uid, "delete")
        await callback.answer("Нет доступа к этой задаче.", show_alert=True)
        return
    await task.delete()
    logger.info(f"Task {task.id} deleted by {uid}")
    await callback.answer("Удалено 🗑")
    await callback.message.delete()
