from bot.constants import MAX_CATEGORY_BYTES
from bot.validators import is_category_too_long


def test_short_category_is_fine():
    assert is_category_too_long("Кухня") is False


def test_exactly_at_limit_is_fine():
    category = "x" * MAX_CATEGORY_BYTES
    assert is_category_too_long(category) is False


def test_one_byte_over_limit_is_too_long():
    category = "x" * (MAX_CATEGORY_BYTES + 1)
    assert is_category_too_long(category) is True


def test_multibyte_characters_count_as_bytes_not_chars():
    # каждый кириллический символ - 2 байта в UTF-8
    chars_that_fit = MAX_CATEGORY_BYTES // 2
    assert is_category_too_long("ы" * chars_that_fit) is False
    assert is_category_too_long("ы" * (chars_that_fit + 1)) is True
