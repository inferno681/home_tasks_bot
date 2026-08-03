from bot.constants import MAX_CATEGORY_BYTES


def is_category_too_long(category: str) -> bool:
    """Would this overflow Telegram's 64-byte callback_data limit?"""
    return len(category.encode("utf-8")) > MAX_CATEGORY_BYTES
