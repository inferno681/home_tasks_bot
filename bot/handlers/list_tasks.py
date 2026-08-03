import logging
from datetime import datetime, timezone
from typing import List, Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from beanie import PydanticObjectId
from beanie.operators import AddToSet, And, In, Or, Set
from bson.errors import InvalidId

from bot.authz import is_authorized
from bot.constants import (
    CB_ASSIGN_ACCEPT_PREFIX,
    CB_ASSIGN_DECLINE_PREFIX,
    CB_SHARE_ACCEPT_PREFIX,
    CB_SHARE_DECLINE_PREFIX,
    CB_TASK_DELETE_PREFIX,
    CB_TASK_DONE_PREFIX,
    MENU_ASSIGN,
    MENU_LIST,
    MENU_SHARE,
    STARTLINK_ASSIGN,
    STARTLINK_SHARE,
    WEEKDAY_NAMES,
)
from bot.deeplinks import notify_unregistered
from bot.display import display_name
from bot.enums import Messages, TaskStatus
from bot.handlers.common import ensure_timezone
from bot.keyboards import assign_confirm_kb, share_confirm_kb, task_actions_kb
from bot.models import Pool, Task, User
from bot.recurrence import next_due_date
from bot.safe_edit import (
    safe_delete,
    safe_edit_reply_markup,
    safe_edit_text,
    safe_notify,
)
from bot.timeutils import to_local, user_offset

logger = logging.getLogger(__name__)

router = Router()


async def _open_tasks_for(
    uid: int, category: Optional[str] = None
) -> List[Task]:
    my_pools = await Pool.find(Pool.members == uid).to_list()
    pool_ids = [pool.id for pool in my_pools]
    conditions = [
        Or(
            And(Task.pool_id == None, Task.user_id == uid),  # noqa: E711
            In(Task.pool_id, pool_ids),
            Task.shared_with == uid,
        ),
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


async def _authorized(task: Task, uid: int) -> bool:
    is_pool_member = False
    if task.pool_id:
        pool = await Pool.get(task.pool_id)
        is_pool_member = bool(pool and uid in pool.members)
    return is_authorized(
        task.user_id, task.shared_with, uid, is_pool_member
    )


async def _caption(task: Task, offset: int) -> str:
    lines = [
        task.text or Messages.NO_TEXT,
        Messages.TASK_ID_LINE.format(task_id=task.id),
    ]
    if task.category:
        lines.append(Messages.CATEGORY_TAG.format(category=task.category))
    if task.pool_id:
        pool = await Pool.get(task.pool_id)
        if pool:
            lines.append(Messages.POOL_TAG.format(pool=pool.name))
    if task.due_at:
        local_due = to_local(task.due_at, offset)
        when = local_due.strftime("%d.%m.%Y %H:%M")
        lines.append(Messages.DUE_LINE.format(when=when))
    if task.assigned_to:
        assignee = await User.find_one(User.user_id == task.assigned_to)
        if assignee and assignee.username:
            lines.append(
                Messages.ASSIGNEE_LINE.format(username=assignee.username)
            )
    if task.repeat_every_days:
        lines.append(
            Messages.REPEAT_DAYS_TAG.format(days=task.repeat_every_days)
        )
    if task.repeat_weekdays:
        days = ", ".join(WEEKDAY_NAMES[i] for i in task.repeat_weekdays)
        lines.append(Messages.REPEAT_WEEKDAYS_TAG.format(days=days))
    if task.completed_history:
        last = to_local(task.completed_history[-1], offset)
        when = last.strftime("%d.%m.%Y %H:%M")
        lines.append(Messages.LAST_DONE_LINE.format(when=when))
    return "\n".join(lines)


@router.message(Command("list"))
@router.message(F.text == MENU_LIST)
async def cmd_list(
    message: Message,
    state: FSMContext,
    command: CommandObject = CommandObject(command="list"),
):
    if not await ensure_timezone(message, state):
        return

    uid = message.from_user.id
    category = (command.args or "").strip() or None
    tasks = await _open_tasks_for(uid, category)

    if not tasks:
        await message.answer(Messages.NO_OPEN_TASKS)
        return

    user = await User.find_one(User.user_id == uid)
    offset = user_offset(user.utc_offset_minutes if user else None)

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
@router.message(F.text == MENU_SHARE)
async def cmd_share(
    message: Message, command: CommandObject = CommandObject(command="share")
):
    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2:
        await message.answer(Messages.SHARE_FORMAT)
        return

    task_id = args[0]
    username = args[1].lstrip("@").lower()
    uid = message.from_user.id

    task = await _get_task(task_id)
    if not task:
        await message.answer(Messages.TASK_NOT_FOUND)
        return
    if task.user_id != uid:
        await message.answer(Messages.SHARE_OWNER_ONLY)
        return

    target = await User.find_one(User.username == username)
    if not target:
        await notify_unregistered(message, STARTLINK_SHARE, task.id, uid)
        return
    if target.user_id == uid or target.user_id in task.shared_with:
        await message.answer(Messages.ALREADY_SHARED)
        return

    requester = await User.find_one(User.user_id == uid)
    await message.bot.send_message(
        target.user_id,
        Messages.SHARE_REQUEST_RECEIVED.format(
            username=display_name(requester, uid),
            text=task.text or Messages.NO_TEXT,
        ),
        reply_markup=share_confirm_kb(task.id, uid),
    )
    logger.info(f"User {uid} sent a share request for task {task.id}")
    await message.answer(Messages.SHARE_REQUEST_SENT.format(username=username))


@router.message(Command("assign"))
@router.message(F.text == MENU_ASSIGN)
async def cmd_assign(
    message: Message,
    command: CommandObject = CommandObject(command="assign"),
):
    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2:
        await message.answer(Messages.ASSIGN_FORMAT)
        return

    task_id = args[0]
    username = args[1].lstrip("@").lower()
    uid = message.from_user.id

    task = await _get_task(task_id)
    if not task:
        await message.answer(Messages.TASK_NOT_FOUND)
        return
    if task.user_id != uid:
        await message.answer(Messages.ASSIGN_OWNER_ONLY)
        return

    target = await User.find_one(User.username == username)
    if not target:
        await notify_unregistered(message, STARTLINK_ASSIGN, task.id, uid)
        return
    if target.user_id == task.assigned_to:
        await message.answer(Messages.ASSIGN_ALREADY)
        return

    requester = await User.find_one(User.user_id == uid)
    await message.bot.send_message(
        target.user_id,
        Messages.ASSIGN_REQUEST_RECEIVED.format(
            username=display_name(requester, uid),
            text=task.text or Messages.NO_TEXT,
        ),
        reply_markup=assign_confirm_kb(task.id, uid),
    )
    logger.info(f"User {uid} sent an assign request for task {task.id}")
    await message.answer(
        Messages.ASSIGN_REQUEST_SENT.format(username=username)
    )


def _log_denied(task: Optional[Task], uid: int, action: str) -> None:
    if task is not None:
        logger.warning(f"User {uid} denied {action} on task {task.id}")


@router.callback_query(F.data.startswith(CB_SHARE_ACCEPT_PREFIX))
async def cb_share_accept(callback: CallbackQuery):
    task_id_raw, requester_id_raw = callback.data.split(":", 2)[1:]
    task = await _get_task(task_id_raw)
    requester_id = int(requester_id_raw)
    accepter_id = callback.from_user.id
    # requester_id приходит из callback_data, которую в обход /share можно
    # получить через подделанный /start-диплинк — перепроверяем владельца
    # по текущим данным, а не доверяем чужому вводу.
    if not task or task.user_id != requester_id:
        await callback.answer(Messages.INVITE_EXPIRED, show_alert=True)
        return

    await task.update(AddToSet({Task.shared_with: accepter_id}))
    logger.info(f"Task {task.id} share accepted by {accepter_id}")
    await callback.answer()
    await safe_edit_text(callback.message, Messages.SHARE_ACCEPTED)
    accepter = await User.find_one(User.user_id == accepter_id)
    await safe_notify(
        callback.bot,
        requester_id,
        Messages.SHARE_ACCEPTED_NOTIFY.format(
            username=display_name(accepter, accepter_id)
        ),
    )


@router.callback_query(F.data.startswith(CB_SHARE_DECLINE_PREFIX))
async def cb_share_decline(callback: CallbackQuery):
    task_id_raw, requester_id_raw = callback.data.split(":", 2)[1:]
    task = await _get_task(task_id_raw)
    requester_id = int(requester_id_raw)
    decliner_id = callback.from_user.id

    await callback.answer()
    await safe_edit_text(callback.message, Messages.SHARE_DECLINED)
    if not task or task.user_id != requester_id:
        return
    decliner = await User.find_one(User.user_id == decliner_id)
    await safe_notify(
        callback.bot,
        requester_id,
        Messages.SHARE_DECLINE_NOTIFY.format(
            username=display_name(decliner, decliner_id)
        ),
    )


@router.callback_query(F.data.startswith(CB_ASSIGN_ACCEPT_PREFIX))
async def cb_assign_accept(callback: CallbackQuery):
    task_id_raw, requester_id_raw = callback.data.split(":", 2)[1:]
    task = await _get_task(task_id_raw)
    requester_id = int(requester_id_raw)
    accepter_id = callback.from_user.id
    if not task or task.user_id != requester_id:
        await callback.answer(Messages.INVITE_EXPIRED, show_alert=True)
        return

    await task.update(
        Set({Task.assigned_to: accepter_id}),
        AddToSet({Task.shared_with: accepter_id}),
    )
    logger.info(f"Task {task.id} assignment accepted by {accepter_id}")
    await callback.answer()
    await safe_edit_text(callback.message, Messages.ASSIGN_ACCEPTED)
    accepter = await User.find_one(User.user_id == accepter_id)
    await safe_notify(
        callback.bot,
        requester_id,
        Messages.ASSIGN_ACCEPTED_NOTIFY.format(
            username=display_name(accepter, accepter_id)
        ),
    )


@router.callback_query(F.data.startswith(CB_ASSIGN_DECLINE_PREFIX))
async def cb_assign_decline(callback: CallbackQuery):
    task_id_raw, requester_id_raw = callback.data.split(":", 2)[1:]
    task = await _get_task(task_id_raw)
    requester_id = int(requester_id_raw)
    decliner_id = callback.from_user.id

    await callback.answer()
    await safe_edit_text(callback.message, Messages.ASSIGN_DECLINED)
    if not task or task.user_id != requester_id:
        return
    decliner = await User.find_one(User.user_id == decliner_id)
    await safe_notify(
        callback.bot,
        requester_id,
        Messages.ASSIGN_DECLINE_NOTIFY.format(
            username=display_name(decliner, decliner_id)
        ),
    )


@router.callback_query(F.data.startswith(CB_TASK_DONE_PREFIX))
async def cb_done(callback: CallbackQuery):
    task_id = callback.data.split(":", 1)[1]
    task = await _get_task(task_id)
    uid = callback.from_user.id
    if not task or not await _authorized(task, uid):
        _log_denied(task, uid, "done")
        await callback.answer(Messages.NO_ACCESS, show_alert=True)
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
        await callback.answer(Messages.TASK_RESCHEDULED)
        await safe_edit_reply_markup(callback.message)
        return

    await task.update(Set({Task.status: TaskStatus.DONE}))
    logger.info(f"Task {task.id} marked done by {uid}")
    await callback.answer(Messages.TASK_DONE)
    await safe_edit_reply_markup(callback.message)


@router.callback_query(F.data.startswith(CB_TASK_DELETE_PREFIX))
async def cb_delete(callback: CallbackQuery):
    task_id = callback.data.split(":", 1)[1]
    task = await _get_task(task_id)
    uid = callback.from_user.id
    if not task or not await _authorized(task, uid):
        _log_denied(task, uid, "delete")
        await callback.answer(Messages.NO_ACCESS, show_alert=True)
        return
    await task.delete()
    logger.info(f"Task {task.id} deleted by {uid}")
    await callback.answer(Messages.TASK_DELETED)
    await safe_delete(callback.message)
