import logging
from typing import Optional, Tuple, Union

from aiogram.types import InlineKeyboardMarkup, Message
from beanie import PydanticObjectId
from bson.errors import InvalidId

from bot.constants import STARTLINK_ASSIGN, STARTLINK_POOL, STARTLINK_SHARE
from bot.display import display_name
from bot.enums import Messages
from bot.keyboards import (
    assign_confirm_kb,
    pool_invite_confirm_kb,
    share_confirm_kb,
)
from bot.models import Pool, Task, User

logger = logging.getLogger(__name__)

ConfirmCard = Tuple[str, InlineKeyboardMarkup]


def build_start_payload(
    kind: str, entity_id: PydanticObjectId, requester_id: int
) -> str:
    """Encode a pending share/assign/pool-invite as a /start deep-link."""
    return f"{kind}_{entity_id}_{requester_id}"


def build_start_link(bot_username: str, payload: str) -> str:
    return f"https://t.me/{bot_username}?start={payload}"


async def notify_unregistered(
    message: Message,
    kind: str,
    entity_id: PydanticObjectId,
    requester_id: int,
) -> None:
    """Tell the requester the target isn't registered, with an invite link."""
    payload = build_start_payload(kind, entity_id, requester_id)
    bot_user = await message.bot.get_me()
    link = build_start_link(bot_user.username, payload)
    await message.answer(Messages.USER_NOT_REGISTERED.format(link=link))


async def _resolve_share(
    entity_id: PydanticObjectId, requester_id: int, username: Union[str, int]
) -> Optional[ConfirmCard]:
    task = await Task.get(entity_id)
    # requester_id — необработанные данные из /start-payload, которые
    # пользователь может набрать сам; без этой сверки кто угодно мог бы
    # выдать себя за владельца чужой задачи и одобрить себе доступ.
    if not task or task.user_id != requester_id:
        return None
    text = Messages.SHARE_REQUEST_RECEIVED.format(
        username=username, text=task.text or Messages.NO_TEXT
    )
    return text, share_confirm_kb(task.id, requester_id)


async def _resolve_assign(
    entity_id: PydanticObjectId, requester_id: int, username: Union[str, int]
) -> Optional[ConfirmCard]:
    task = await Task.get(entity_id)
    if not task or task.user_id != requester_id:
        return None
    text = Messages.ASSIGN_REQUEST_RECEIVED.format(
        username=username, text=task.text or Messages.NO_TEXT
    )
    return text, assign_confirm_kb(task.id, requester_id)


async def _resolve_pool(
    entity_id: PydanticObjectId, requester_id: int, username: Union[str, int]
) -> Optional[ConfirmCard]:
    pool = await Pool.get(entity_id)
    if not pool or requester_id not in pool.members:
        return None
    text = Messages.POOL_INVITE_RECEIVED.format(
        username=username, pool=pool.name
    )
    return text, pool_invite_confirm_kb(pool.id, requester_id)


_RESOLVERS = {
    STARTLINK_SHARE: _resolve_share,
    STARTLINK_ASSIGN: _resolve_assign,
    STARTLINK_POOL: _resolve_pool,
}


async def resolve_pending_action(payload: str) -> Optional[ConfirmCard]:
    """Turn a /start deep-link payload back into the same confirm card.

    Returns None if the payload is malformed or the underlying task/pool no
    longer exists (deleted between the invite and the /start click).
    """
    parts = payload.split("_")
    if len(parts) != 3:
        return None
    kind, entity_id_raw, requester_id_raw = parts
    resolver = _RESOLVERS.get(kind)
    if resolver is None:
        return None

    try:
        entity_id = PydanticObjectId(entity_id_raw)
        requester_id = int(requester_id_raw)
    except (InvalidId, ValueError):
        return None

    requester = await User.find_one(User.user_id == requester_id)
    username = display_name(requester, requester_id)
    return await resolver(entity_id, requester_id, username)
