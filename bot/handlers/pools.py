import logging
import re
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from beanie import PydanticObjectId
from beanie.operators import AddToSet, Pull, Set

from bot.callback_parse import parse_int, parse_object_id
from bot.constants import (
    CB_POOL_INVITE_ACCEPT_PREFIX,
    CB_POOL_INVITE_DECLINE_PREFIX,
    MENU_POOLS,
    STARTLINK_POOL,
)
from bot.deeplinks import notify_unregistered
from bot.display import display_name
from bot.enums import Messages
from bot.keyboards import pool_invite_confirm_kb
from bot.models import Pool, User
from bot.safe_edit import safe_edit_text, safe_notify

logger = logging.getLogger(__name__)

router = Router()

# Хвост вида " #a3f9c1" — короткий id пула, который показывают /pools и
# кнопки-выборы, чтобы различить два своих пула с одинаковым названием.
_SHORT_ID_RE = re.compile(r"\s+#([0-9a-f]{6})$", re.IGNORECASE)


async def _resolve_pool(
    message: Message, uid: int, raw_name: str
) -> Optional[Pool]:
    """Find one of the caller's pools by name.

    Accepts an optional trailing "#<short_id>" (as shown by /pools) to
    disambiguate when several of the caller's pools share the same name;
    answers the message itself and returns None if not found or still
    ambiguous without one.
    """
    match = _SHORT_ID_RE.search(raw_name)
    short_id = match.group(1).lower() if match else None
    name = raw_name[: match.start()] if match else raw_name

    candidates = await Pool.find(
        Pool.name == name, Pool.members == uid
    ).to_list()
    if short_id:
        candidates = [pool for pool in candidates if pool.short_id == short_id]

    if not candidates:
        await message.answer(Messages.POOL_NOT_FOUND)
        return None
    if len(candidates) > 1:
        listing = "\n".join(pool.label for pool in candidates)
        await message.answer(
            Messages.POOL_AMBIGUOUS.format(name=name, pools=listing)
        )
        return None
    return candidates[0]


async def _clear_stale_default_pool(
    uid: int, pool_id: PydanticObjectId
) -> None:
    """If a user's default pool is the one they just left/got kicked from,
    reset it to personal — otherwise their next silent-default task would be
    created into a pool they can no longer see (bot/handlers/new_task.py:
    _after_content)."""
    await User.find_one(
        User.user_id == uid, User.default_pool_id == pool_id
    ).update(Set({User.default_pool_id: None}))


@router.message(Command("newpool"))
async def cmd_newpool(
    message: Message,
    command: CommandObject = CommandObject(command="newpool"),
):
    name = (command.args or "").strip()
    if not name:
        await message.answer(Messages.POOL_FORMAT_NEW)
        return

    uid = message.from_user.id
    pool = await Pool(name=name, members=[uid], created_by=uid).insert()
    logger.info(f"Pool {pool.id} {name!r} created by {uid}")
    await message.answer(
        Messages.POOL_CREATED.format(name=name, short_id=pool.short_id)
    )


@router.message(Command("invite"))
async def cmd_invite(
    message: Message, command: CommandObject = CommandObject(command="invite")
):
    args = (command.args or "").rsplit(maxsplit=1)
    if len(args) != 2:
        await message.answer(Messages.POOL_FORMAT_INVITE)
        return

    pool_name, username = args[0], args[1].lstrip("@").lower()
    uid = message.from_user.id

    pool = await _resolve_pool(message, uid, pool_name)
    if not pool:
        return

    target = await User.find_one(User.username == username)
    if not target:
        await notify_unregistered(message, STARTLINK_POOL, pool.id, uid)
        return
    if target.user_id in pool.members:
        await message.answer(
            Messages.POOL_ALREADY_MEMBER.format(pool=pool.name)
        )
        return

    requester = await User.find_one(User.user_id == uid)
    await message.bot.send_message(
        target.user_id,
        Messages.POOL_INVITE_RECEIVED.format(
            username=display_name(requester, uid), pool=pool.name
        ),
        reply_markup=pool_invite_confirm_kb(pool.id, uid),
    )
    logger.info(f"User {uid} invited {target.user_id} to pool {pool.id}")
    await message.answer(
        Messages.POOL_INVITE_SENT.format(pool=pool.name, username=username)
    )


@router.message(Command("pools"))
@router.message(F.text == MENU_POOLS)
async def cmd_pools(message: Message):
    pools = await Pool.find(Pool.members == message.from_user.id).to_list()
    if not pools:
        await message.answer(Messages.POOL_LIST_EMPTY)
        return

    lines = [
        Messages.POOL_LIST_ITEM.format(
            label=pool.label, count=len(pool.members)
        )
        for pool in pools
    ]
    await message.answer("\n".join(lines))


@router.message(Command("leave"))
async def cmd_leave(
    message: Message, command: CommandObject = CommandObject(command="leave")
):
    pool_name = (command.args or "").strip()
    if not pool_name:
        await message.answer(Messages.LEAVE_FORMAT)
        return

    uid = message.from_user.id
    pool = await _resolve_pool(message, uid, pool_name)
    if not pool:
        return

    if len(pool.members) == 1:
        await pool.delete()
    else:
        await pool.update(Pull({Pool.members: uid}))
    await _clear_stale_default_pool(uid, pool.id)
    logger.info(f"User {uid} left pool {pool.id}")
    await message.answer(Messages.LEFT_POOL.format(pool=pool.name))


@router.message(Command("kick"))
async def cmd_kick(
    message: Message, command: CommandObject = CommandObject(command="kick")
):
    args = (command.args or "").rsplit(maxsplit=1)
    if len(args) != 2:
        await message.answer(Messages.KICK_FORMAT)
        return

    pool_name, username = args[0], args[1].lstrip("@").lower()
    uid = message.from_user.id

    pool = await _resolve_pool(message, uid, pool_name)
    if not pool:
        return
    if pool.created_by != uid:
        await message.answer(Messages.KICK_CREATOR_ONLY)
        return

    target = await User.find_one(User.username == username)
    if not target or target.user_id not in pool.members:
        await message.answer(Messages.KICK_NOT_MEMBER.format(pool=pool.name))
        return

    await pool.update(Pull({Pool.members: target.user_id}))
    await _clear_stale_default_pool(target.user_id, pool.id)
    logger.info(f"User {uid} kicked {target.user_id} from pool {pool.id}")
    await message.answer(
        Messages.KICK_SUCCESS.format(pool=pool.name, username=username)
    )
    await message.bot.send_message(
        target.user_id, Messages.KICKED_FROM_POOL.format(pool=pool.name)
    )


@router.callback_query(F.data.startswith(CB_POOL_INVITE_ACCEPT_PREFIX))
async def cb_pool_invite_accept(callback: CallbackQuery):
    pool_id_raw, requester_id_raw = callback.data.split(":", 2)[1:]
    pool_id = parse_object_id(pool_id_raw)
    requester_id = parse_int(requester_id_raw)
    accepter_id = callback.from_user.id

    pool = None if pool_id is None else await Pool.get(pool_id)
    # requester_id приходит из callback_data, которую в обход /invite можно
    # получить через подделанный /start-диплинк — перепроверяем членство
    # по текущим данным, а не доверяем чужому вводу. Оба id вдобавок могут
    # быть просто "мусором" из руками собранного callback_data — parse_*
    # возвращает None вместо падения с ValueError/InvalidId.
    if not pool or requester_id is None or requester_id not in pool.members:
        await callback.answer(Messages.INVITE_EXPIRED, show_alert=True)
        return
    await pool.update(AddToSet({Pool.members: accepter_id}))
    logger.info(f"User {accepter_id} joined pool {pool_id}")

    await callback.answer()
    await safe_edit_text(
        callback.message, Messages.POOL_JOINED.format(pool=pool.name)
    )
    accepter = await User.find_one(User.user_id == accepter_id)
    await safe_notify(
        callback.bot,
        requester_id,
        Messages.POOL_JOIN_NOTIFY.format(
            username=display_name(accepter, accepter_id), pool=pool.name
        ),
    )


@router.callback_query(F.data.startswith(CB_POOL_INVITE_DECLINE_PREFIX))
async def cb_pool_invite_decline(callback: CallbackQuery):
    pool_id_raw, requester_id_raw = callback.data.split(":", 2)[1:]
    requester_id = parse_int(requester_id_raw)
    decliner_id = callback.from_user.id

    pool_id = parse_object_id(pool_id_raw)
    pool = None if pool_id is None else await Pool.get(pool_id)

    await callback.answer()
    await safe_edit_text(callback.message, Messages.POOL_DECLINED)
    if not pool or requester_id is None or requester_id not in pool.members:
        return
    decliner = await User.find_one(User.user_id == decliner_id)
    await safe_notify(
        callback.bot,
        requester_id,
        Messages.POOL_DECLINE_NOTIFY.format(
            username=display_name(decliner, decliner_id), pool=pool.name
        ),
    )
    logger.info(f"User {decliner_id} declined invite to pool {pool_id_raw}")
