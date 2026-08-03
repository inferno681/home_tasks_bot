from bot.authz import is_authorized


def test_owner_is_authorized():
    assert is_authorized(owner_id=1, shared_with=[], uid=1) is True


def test_shared_user_is_authorized():
    assert is_authorized(owner_id=1, shared_with=[2, 3], uid=2) is True


def test_stranger_is_not_authorized():
    assert is_authorized(owner_id=1, shared_with=[2, 3], uid=99) is False


def test_empty_shared_with_only_owner_authorized():
    assert is_authorized(owner_id=1, shared_with=[], uid=2) is False


def test_pool_member_is_authorized():
    assert (
        is_authorized(owner_id=1, shared_with=[], uid=2, is_pool_member=True)
        is True
    )


def test_non_pool_member_is_not_authorized():
    assert (
        is_authorized(owner_id=1, shared_with=[], uid=99, is_pool_member=False)
        is False
    )
