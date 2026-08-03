import pytest

from bot.deeplinks import (
    build_start_link,
    build_start_payload,
    resolve_pending_action,
)
from bot.models import Pool, Task, User

pytestmark = pytest.mark.usefixtures("clean_db")


def test_build_start_link():
    link = build_start_link("mybot", "share_abc_1")
    assert link == "https://t.me/mybot?start=share_abc_1"


async def test_resolve_share_payload(mongo_db):
    task = await Task(user_id=1, text="water plants").insert()
    await User(user_id=1, username="alice").insert()
    payload = build_start_payload("share", task.id, 1)

    resolved = await resolve_pending_action(payload)

    assert resolved is not None
    text, _markup = resolved
    assert "alice" in text
    assert "water plants" in text


async def test_resolve_assign_payload(mongo_db):
    task = await Task(user_id=1, text="take out trash").insert()
    payload = build_start_payload("assign", task.id, 1)

    resolved = await resolve_pending_action(payload)

    assert resolved is not None
    text, _markup = resolved
    assert "take out trash" in text


async def test_resolve_pool_payload(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    payload = build_start_payload("pool", pool.id, 1)

    resolved = await resolve_pending_action(payload)

    assert resolved is not None
    text, _markup = resolved
    assert "Семья" in text


async def test_resolve_returns_none_for_deleted_task(mongo_db):
    task = await Task(user_id=1, text="gone").insert()
    payload = build_start_payload("share", task.id, 1)
    await task.delete()

    assert await resolve_pending_action(payload) is None


async def test_resolve_returns_none_for_malformed_payload(mongo_db):
    assert await resolve_pending_action("not-a-valid-payload") is None
    assert await resolve_pending_action("share_notanid_1") is None
    assert await resolve_pending_action("unknownkind_abc_1") is None


async def test_resolve_share_rejects_forged_requester(mongo_db):
    """Regression: a payload naming someone other than the task's real
    owner as requester_id must not resolve to a working confirm card —
    otherwise anyone who learns a task_id could self-share it."""
    task = await Task(user_id=1, text="not yours").insert()
    forged_payload = build_start_payload("share", task.id, 999)

    assert await resolve_pending_action(forged_payload) is None


async def test_resolve_assign_rejects_forged_requester(mongo_db):
    task = await Task(user_id=1, text="not yours").insert()
    forged_payload = build_start_payload("assign", task.id, 999)

    assert await resolve_pending_action(forged_payload) is None


async def test_resolve_pool_rejects_non_member_requester(mongo_db):
    pool = await Pool(name="Семья", members=[1], created_by=1).insert()
    forged_payload = build_start_payload("pool", pool.id, 999)

    assert await resolve_pending_action(forged_payload) is None
