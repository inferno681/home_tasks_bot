import logging
from typing import Iterable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from beanie.operators import Set

from bot.constants import (
    CB_SETTINGS_ASK_TOGGLE,
    CB_SETTINGS_DEFAULT_POOL_PREFIX,
    CB_SETTINGS_QUIET_PERIOD,
    CB_SETTINGS_QUIET_TOGGLE,
    MAIN_MENU_LABELS,
    MENU_SETTINGS,
    POOL_NONE,
)
from bot.enums import Messages
from bot.keyboards import settings_kb
from bot.models import Pool, User
from bot.pool_access import get_member_pool
from bot.safe_edit import safe_edit_text
from bot.timeutils import parse_quiet_hours_period

logger = logging.getLogger(__name__)

router = Router()


class SettingsFSM(StatesGroup):
    waiting_quiet_period = State()


async def _settings_text(user: User) -> str:
    pool_name: str = Messages.POOL_PERSONAL_NAME
    if user.default_pool_id:
        pool = await Pool.get(user.default_pool_id)
        pool_name = pool.name if pool else Messages.POOL_PERSONAL_NAME
    ask = (
        Messages.SETTINGS_ASK_YES
        if user.ask_pool_on_create
        else Messages.SETTINGS_ASK_NO
    )
    quiet = (
        Messages.QUIET_HOURS_ON_LABEL.format(
            start=user.quiet_hours_start, end=user.quiet_hours_end
        )
        if user.quiet_hours_enabled
        else Messages.QUIET_HOURS_OFF_LABEL
    )
    return "\n".join(
        [
            Messages.SETTINGS_TITLE,
            Messages.SETTINGS_CURRENT.format(
                pool=pool_name, ask=ask, quiet=quiet
            ),
        ]
    )


def _settings_kb(user: User, pools: Iterable[Pool]):
    return settings_kb(
        pools,
        user.default_pool_id,
        user.ask_pool_on_create,
        user.quiet_hours_enabled,
    )


async def _refresh_settings_message(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    user = await User.find_one(User.user_id == uid)
    pools = await Pool.find(Pool.members == uid).to_list()
    await safe_edit_text(
        callback.message, await _settings_text(user), markup=_settings_kb(
            user, pools
        )
    )


@router.message(Command("settings"))
@router.message(F.text == MENU_SETTINGS)
async def cmd_settings(message: Message):
    uid = message.from_user.id
    user = await User.find_one(User.user_id == uid)
    pools = await Pool.find(Pool.members == uid).to_list()
    await message.answer(
        await _settings_text(user),
        reply_markup=_settings_kb(user, pools),
    )


@router.callback_query(F.data.startswith(CB_SETTINGS_DEFAULT_POOL_PREFIX))
async def cb_settings_set_pool(callback: CallbackQuery):
    raw = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    pool_id = None
    if raw != POOL_NONE:
        pool = await get_member_pool(raw, uid)
        if not pool:
            await callback.answer(Messages.POOL_NOT_FOUND, show_alert=True)
            return
        pool_id = pool.id

    await User.find_one(User.user_id == uid).update(
        Set({User.default_pool_id: pool_id})
    )
    await callback.answer()
    await _refresh_settings_message(callback)


@router.callback_query(F.data == CB_SETTINGS_ASK_TOGGLE)
async def cb_settings_toggle_ask(callback: CallbackQuery):
    user = await User.find_one(User.user_id == callback.from_user.id)
    await user.update(
        Set({User.ask_pool_on_create: not user.ask_pool_on_create})
    )
    await callback.answer()
    await _refresh_settings_message(callback)


@router.callback_query(F.data == CB_SETTINGS_QUIET_TOGGLE)
async def cb_settings_toggle_quiet(callback: CallbackQuery):
    user = await User.find_one(User.user_id == callback.from_user.id)
    await user.update(
        Set({User.quiet_hours_enabled: not user.quiet_hours_enabled})
    )
    await callback.answer()
    await _refresh_settings_message(callback)


@router.callback_query(F.data == CB_SETTINGS_QUIET_PERIOD)
async def cb_settings_quiet_period_prompt(
    callback: CallbackQuery, state: FSMContext
):
    await state.set_state(SettingsFSM.waiting_quiet_period)
    await callback.answer()
    await callback.message.answer(Messages.ASK_QUIET_HOURS_PERIOD)


@router.message(
    SettingsFSM.waiting_quiet_period, F.text, ~F.text.in_(MAIN_MENU_LABELS)
)
async def settings_quiet_period_set(message: Message, state: FSMContext):
    parsed = parse_quiet_hours_period(message.text)
    if parsed is None:
        await message.answer(Messages.INVALID_QUIET_HOURS_PERIOD)
        return

    start, end = parsed
    uid = message.from_user.id
    await User.find_one(User.user_id == uid).update(
        Set({User.quiet_hours_start: start, User.quiet_hours_end: end})
    )
    await state.clear()
    await message.answer(
        Messages.QUIET_HOURS_PERIOD_SAVED.format(start=start, end=end)
    )

    user = await User.find_one(User.user_id == uid)
    pools = await Pool.find(Pool.members == uid).to_list()
    await message.answer(
        await _settings_text(user),
        reply_markup=_settings_kb(user, pools),
    )
