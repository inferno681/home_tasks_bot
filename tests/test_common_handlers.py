from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from bot.deeplinks import build_start_payload
from bot.enums import Messages
from bot.handlers.common import SetTimezone, cmd_help, cmd_start, set_timezone
from bot.models import Task, User

pytestmark = pytest.mark.usefixtures("clean_db")


def _fsm(user_id=1):
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id),
    )


def _message(uid=1, text=None):
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=uid, username=None)
    message.text = text
    message.answer = AsyncMock()
    return message


async def test_start_asks_timezone_for_new_user(mongo_db):
    state = _fsm()
    message = _message(uid=1)

    await cmd_start(message, state)

    message.answer.assert_awaited_once_with(Messages.ASK_TIMEZONE)
    assert await state.get_state() == SetTimezone.waiting_offset


async def test_start_greets_known_user(mongo_db):
    await User(user_id=1, utc_offset_minutes=180).insert()
    state = _fsm()
    message = _message(uid=1)

    await cmd_start(message, state)

    assert message.answer.await_args.kwargs["reply_markup"] is not None
    assert await state.get_state() is None


async def test_start_with_payload_shows_confirm_card_immediately(mongo_db):
    await User(user_id=1, utc_offset_minutes=180).insert()
    task = await Task(user_id=2, text="mow the lawn").insert()
    payload = build_start_payload("share", task.id, 2)
    state = _fsm()
    message = _message(uid=1)

    await cmd_start(
        message, state, CommandObject(command="start", args=payload)
    )

    assert message.answer.await_count == 2
    calls = message.answer.await_args_list
    confirm_text = calls[1].args[0]
    assert "mow the lawn" in confirm_text


async def test_start_with_payload_defers_until_timezone_is_set(mongo_db):
    task = await Task(user_id=2, text="wash the car").insert()
    payload = build_start_payload("share", task.id, 2)
    state = _fsm()
    message = _message(uid=1)

    await cmd_start(
        message, state, CommandObject(command="start", args=payload)
    )

    message.answer.assert_awaited_once_with(Messages.ASK_TIMEZONE)
    assert (await state.get_data())["pending_payload"] == payload

    message.text = "+3"
    await set_timezone(message, state)

    calls = message.answer.await_args_list
    confirm_text = calls[-1].args[0]
    assert "wash the car" in confirm_text


async def test_start_with_unresolvable_payload_shows_only_welcome(mongo_db):
    """A malformed/expired deep-link payload must not crash cmd_start — it
    just silently skips the confirm card."""
    await User(user_id=1, utc_offset_minutes=180).insert()
    state = _fsm()
    message = _message(uid=1)

    await cmd_start(
        message, state, CommandObject(command="start", args="bogus")
    )

    message.answer.assert_awaited_once()


async def test_set_timezone_rejects_invalid_offset(mongo_db):
    state = _fsm()
    await state.set_state(SetTimezone.waiting_offset)

    await set_timezone(_message(uid=1, text="not-an-offset"), state)

    assert await User.find_one(User.user_id == 1) is None
    assert await state.get_state() == SetTimezone.waiting_offset


async def test_set_timezone_saves_offset_and_clears_state(mongo_db):
    state = _fsm()
    await state.set_state(SetTimezone.waiting_offset)

    await set_timezone(_message(uid=1, text="+3"), state)

    user = await User.find_one(User.user_id == 1)
    assert user.utc_offset_minutes == 180
    assert await state.get_state() is None


async def test_help_answers_with_help_text(mongo_db):
    message = _message(uid=1)

    await cmd_help(message)

    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == Messages.HELP
