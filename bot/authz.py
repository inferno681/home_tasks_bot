from typing import Iterable


def is_authorized(
    owner_id: int,
    shared_with: Iterable[int],
    uid: int,
    is_pool_member: bool = False,
) -> bool:
    """Is `uid` the owner, in `shared_with`, or a member of the task's pool?"""
    return owner_id == uid or uid in shared_with or is_pool_member
