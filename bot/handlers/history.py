import logging
import math

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from beanie.operators import And, In, Or

from bot.constants import (
    CB_HISTORY_PAGE_PREFIX,
    HISTORY_PAGE_SIZE,
    MENU_HISTORY,
)
from bot.enums import Messages, TaskStatus
from bot.handlers.common import ensure_timezone
from bot.keyboards import history_nav_kb
from bot.models import Pool, Task, User
from bot.safe_edit import safe_edit_text
from bot.timeutils import to_local, user_offset

logger = logging.getLogger(__name__)

router = Router()


async def _history_tasks_for(
    uid: int, page: int
) -> tuple[list[Task], int]:
    my_pools = await Pool.find(Pool.members == uid).to_list()
    pool_ids = [pool.id for pool in my_pools]
    query = Task.find(
        Or(
            And(Task.pool_id == None, Task.user_id == uid),  # noqa: E711
            In(Task.pool_id, pool_ids),
            Task.shared_with == uid,
        ),
        Task.status == TaskStatus.DONE,
    ).sort("-completed_at")
    total = await query.count()
    tasks = await query.skip(page * HISTORY_PAGE_SIZE).limit(
        HISTORY_PAGE_SIZE
    ).to_list()
    return tasks, total


def _history_line(task: Task, offset: int) -> str:
    lines = [task.text or Messages.NO_TEXT]
    if task.category:
        lines.append(Messages.CATEGORY_TAG.format(category=task.category))
    if task.completed_at:
        local_done = to_local(task.completed_at, offset)
        when = local_done.strftime("%d.%m.%Y %H:%M")
        lines.append(Messages.HISTORY_DONE_AT.format(when=when))
    return "\n".join(lines)


async def _render_history(
    uid: int, page: int
) -> tuple[str, InlineKeyboardMarkup | None]:
    tasks, total = await _history_tasks_for(uid, page)
    if not tasks:
        return Messages.HISTORY_EMPTY, None

    user = await User.find_one(User.user_id == uid)
    offset = user_offset(user.utc_offset_minutes if user else None)
    pages = math.ceil(total / HISTORY_PAGE_SIZE)
    blocks = [Messages.HISTORY_TITLE.format(page=page + 1, pages=pages)]
    blocks.extend(_history_line(task, offset) for task in tasks)
    text = "\n\n".join(blocks)
    kb = history_nav_kb(
        page,
        has_prev=page > 0,
        has_next=(page + 1) * HISTORY_PAGE_SIZE < total,
    )
    return text, kb


@router.message(Command("history"))
@router.message(F.text == MENU_HISTORY)
async def cmd_history(message: Message, state: FSMContext):
    if not await ensure_timezone(message, state):
        return
    text, kb = await _render_history(message.from_user.id, 0)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith(CB_HISTORY_PAGE_PREFIX))
async def cb_history_page(callback: CallbackQuery):
    page = int(callback.data.split(":", 1)[1])
    text, kb = await _render_history(callback.from_user.id, page)
    await callback.answer()
    await safe_edit_text(callback.message, text, kb)
