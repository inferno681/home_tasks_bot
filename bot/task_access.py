from typing import Optional

from bot.authz import is_authorized
from bot.callback_parse import parse_object_id
from bot.models import Pool, Task


async def get_task(task_id: str) -> Optional[Task]:
    object_id = parse_object_id(task_id)
    if object_id is None:
        return None
    task = await Task.get(object_id)
    if task and task.deleted_at is not None:
        return None
    return task


async def get_deleted_task(task_id: str, uid: int) -> Optional[Task]:
    """Fetch a soft-deleted task for the undo flow — the only place that
    intentionally looks past get_task()'s "not deleted" filter."""
    object_id = parse_object_id(task_id)
    if object_id is None:
        return None
    task = await Task.get(object_id)
    if not task or task.deleted_at is None:
        return None
    if not await is_task_authorized(task, uid):
        return None
    return task


async def is_task_authorized(task: Task, uid: int) -> bool:
    is_pool_member = False
    if task.pool_id:
        pool = await Pool.get(task.pool_id)
        is_pool_member = bool(pool and uid in pool.members)
    return is_authorized(task.user_id, task.shared_with, uid, is_pool_member)
