import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from beanie import PydanticObjectId
from beanie.operators import Set

from bot.constants import (
    CB_SETTINGS_ASK_TOGGLE,
    CB_SETTINGS_DEFAULT_POOL_PREFIX,
    MENU_SETTINGS,
    POOL_NONE,
)
from bot.enums import Messages
from bot.keyboards import settings_kb
from bot.models import Pool, User
from bot.safe_edit import safe_edit_text

logger = logging.getLogger(__name__)

router = Router()


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
    return "\n".join(
        [
            Messages.SETTINGS_TITLE,
            Messages.SETTINGS_CURRENT.format(pool=pool_name, ask=ask),
        ]
    )


async def _refresh_settings_message(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    user = await User.find_one(User.user_id == uid)
    pools = await Pool.find(Pool.members == uid).to_list()
    await safe_edit_text(
        callback.message,
        await _settings_text(user),
        markup=settings_kb(
            pools, user.default_pool_id, user.ask_pool_on_create
        ),
    )


@router.message(Command("settings"))
@router.message(F.text == MENU_SETTINGS)
async def cmd_settings(message: Message):
    uid = message.from_user.id
    user = await User.find_one(User.user_id == uid)
    pools = await Pool.find(Pool.members == uid).to_list()
    await message.answer(
        await _settings_text(user),
        reply_markup=settings_kb(
            pools, user.default_pool_id, user.ask_pool_on_create
        ),
    )


@router.callback_query(F.data.startswith(CB_SETTINGS_DEFAULT_POOL_PREFIX))
async def cb_settings_set_pool(callback: CallbackQuery):
    raw = callback.data.split(":", 1)[1]
    pool_id = None if raw == POOL_NONE else PydanticObjectId(raw)

    await User.find_one(User.user_id == callback.from_user.id).update(
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
