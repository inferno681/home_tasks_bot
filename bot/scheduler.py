import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from beanie.operators import Set

from bot.enums import Messages, TaskStatus
from bot.models import Pool, Task
from config.config import config

logger = logging.getLogger(__name__)


async def _reminder_recipients(task: Task) -> list[int]:
    """Owner + shared_with + the task's pool members — deduped."""
    pool_members: list[int] = []
    if task.pool_id:
        pool = await Pool.get(task.pool_id)
        pool_members = pool.members if pool else []
    return sorted({task.user_id, *task.shared_with, *pool_members})


async def _send_reminder(bot: Bot, task: Task, recipient: int) -> bool:
    """Send one reminder to one recipient; returns whether it went through."""
    text = Messages.REMINDER.format(text=task.text or Messages.NO_TEXT)
    try:
        if task.photo_file_id:
            await bot.send_photo(
                recipient, task.photo_file_id, caption=text
            )
        else:
            await bot.send_message(recipient, text)
    except Exception as e:
        # ponytail: если чат заблокирован навсегда, будет ретраиться каждый
        # интервал бесконечно (пока хоть кто-то в пуле не получит) — апгрейд:
        # отдельно ловить TelegramForbiddenError для этого получателя.
        logger.warning(
            f"Не удалось отправить напоминание по задаче {task.id} "
            f"пользователю {recipient}: {e}"
        )
        return False
    logger.info(f"Reminder sent for task {task.id} to user {recipient}")
    return True


async def check_reminders(bot: Bot):
    now = datetime.now(timezone.utc)
    tasks = await Task.find(
        Task.status == TaskStatus.PENDING,
        Task.reminded == False,  # noqa: E712
        Task.due_at != None,  # noqa: E711
        Task.due_at <= now,
    ).to_list()

    for task in tasks:
        recipients = await _reminder_recipients(task)
        # Помечаем разосланным, если дошло хотя бы до одного получателя —
        # иначе один заблокировавший бота участник пула держит остальных
        # на бесконечном ретрае.
        delivered = [
            await _send_reminder(bot, task, recipient)
            for recipient in recipients
        ]
        if any(delivered):
            await task.update(Set({Task.reminded: True}))


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_reminders,
        "interval",
        seconds=config.scheduler.interval_seconds,
        args=(bot,),
    )
    return scheduler
