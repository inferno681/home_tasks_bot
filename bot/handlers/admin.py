from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.enums import Messages, TaskStatus
from bot.models import Pool, Task, User
from config.config import config

router = Router()


def _is_admin(uid: int) -> bool:
    admin_id = config.secrets.admin_id
    return admin_id is not None and uid == admin_id


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer(Messages.ADMIN_ONLY)
        return

    users = await User.find().count()
    pools = await Pool.find().count()
    tasks = await Task.find().count()
    pending = await Task.find(Task.status == TaskStatus.PENDING).count()
    done = await Task.find(Task.status == TaskStatus.DONE).count()

    await message.answer(
        Messages.STATS.format(
            users=users,
            pools=pools,
            tasks=tasks,
            pending=pending,
            done=done,
        )
    )
