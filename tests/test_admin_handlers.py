from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from bot.enums import Messages, TaskStatus
from bot.handlers.admin import cmd_stats
from bot.models import Pool, Task, User
from config.config import config

pytestmark = pytest.mark.usefixtures("clean_db")


def _message(uid):
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=uid)
    message.answer = AsyncMock()
    return message


async def test_stats_denies_non_admin(mongo_db, monkeypatch):
    monkeypatch.setattr(config.secrets, "admin_id", 999)
    message = _message(1)

    await cmd_stats(message)

    message.answer.assert_awaited_once_with(Messages.ADMIN_ONLY)


async def test_stats_denies_when_admin_not_configured(mongo_db, monkeypatch):
    monkeypatch.setattr(config.secrets, "admin_id", None)
    message = _message(1)

    await cmd_stats(message)

    message.answer.assert_awaited_once_with(Messages.ADMIN_ONLY)


async def test_stats_shows_counts_for_admin(mongo_db, monkeypatch):
    monkeypatch.setattr(config.secrets, "admin_id", 1)
    await User(user_id=1).insert()
    await User(user_id=2).insert()
    await Pool(name="p", created_by=1).insert()
    await Task(user_id=1, text="a", status=TaskStatus.PENDING).insert()
    await Task(user_id=1, text="b", status=TaskStatus.DONE).insert()
    message = _message(1)

    await cmd_stats(message)

    message.answer.assert_awaited_once_with(
        Messages.STATS.format(users=2, pools=1, tasks=2, pending=1, done=1)
    )


async def test_stats_excludes_soft_deleted_tasks(mongo_db, monkeypatch):
    """Regression: /stats must not count tasks the user has thrown away —
    a soft-deleted task previously still showed up as open/total."""
    monkeypatch.setattr(config.secrets, "admin_id", 1)
    await User(user_id=1).insert()
    await Task(user_id=1, text="alive", status=TaskStatus.PENDING).insert()
    await Task(
        user_id=1,
        text="deleted",
        status=TaskStatus.PENDING,
        deleted_at=datetime.now(timezone.utc),
    ).insert()
    message = _message(1)

    await cmd_stats(message)

    message.answer.assert_awaited_once_with(
        Messages.STATS.format(users=1, pools=0, tasks=1, pending=1, done=0)
    )
