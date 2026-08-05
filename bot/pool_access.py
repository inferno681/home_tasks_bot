from typing import Optional

from bot.callback_parse import parse_object_id
from bot.models import Pool


async def get_member_pool(raw_id: str, uid: int) -> Optional[Pool]:
    """Resolve a client-supplied pool id, but only if `uid` is a member.

    A pool id from callback_data is as untrustworthy as any other client
    input (see bot/task_access.py) — without this check, a forged id could
    attach a task, or a user's default pool, to a pool its owner was never
    invited to, silently exposing that content to the pool's real members.
    """
    pool_id = parse_object_id(raw_id)
    if pool_id is None:
        return None
    pool = await Pool.get(pool_id)
    if not pool or uid not in pool.members:
        return None
    return pool
