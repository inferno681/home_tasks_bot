from bot.callback_parse import parse_int, parse_object_id


def test_parse_int_valid():
    assert parse_int("42") == 42


def test_parse_int_invalid():
    assert parse_int("not-an-int") is None


def test_parse_object_id_valid():
    raw = "507f1f77bcf86cd799439011"
    assert str(parse_object_id(raw)) == raw


def test_parse_object_id_invalid():
    assert parse_object_id("not-an-object-id") is None
