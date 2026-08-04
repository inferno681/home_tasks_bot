from typing import Optional

from beanie import PydanticObjectId
from bson.errors import InvalidId

from bot.authz import is_authorized
from bot.models import Pool, Task


async def get_task(task_id: str) -> Optional[Task]:
    try:
        object_id = PydanticObjectId(task_id)
    except InvalidId:
        return None
    return await Task.get(object_id)


async def is_task_authorized(task: Task, uid: int) -> bool:
    is_pool_member = False
    if task.pool_id:
        pool = await Pool.get(task.pool_id)
        is_pool_member = bool(pool and uid in pool.members)
    return is_authorized(task.user_id, task.shared_with, uid, is_pool_member)
