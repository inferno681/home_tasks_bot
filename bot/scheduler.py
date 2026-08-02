import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.models import Task, TaskStatus
from config.config import config

logger = logging.getLogger(__name__)


async def _send_reminder(bot: Bot, task: Task) -> bool:
    """Send one reminder; returns whether it went through."""
    text = f"⏰ Напоминание: {task.text or '(без текста)'}"
    try:
        if task.photo_file_id:
            await bot.send_photo(
                task.user_id, task.photo_file_id, caption=text
            )
        else:
            await bot.send_message(task.user_id, text)
    except Exception as e:
        # ponytail: если чат заблокирован навсегда, будет ретраиться каждый
        # интервал бесконечно — апгрейд: отдельно ловить
        # TelegramForbiddenError и всё равно гасить reminded.
        logger.warning(
            f"Не удалось отправить напоминание по задаче {task.id}: {e}"
        )
        return False
    logger.info(f"Reminder sent for task {task.id} to user {task.user_id}")
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
        if await _send_reminder(bot, task):
            task.reminded = True
            await task.save()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_reminders,
        "interval",
        seconds=config.scheduler.interval_seconds,
        args=(bot,),
    )
    return scheduler
