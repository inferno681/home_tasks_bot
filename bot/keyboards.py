from typing import Iterable, Optional

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from beanie import PydanticObjectId

from bot.constants import (
    ACCEPT_BUTTON,
    BACK_BUTTON_TEXT,
    BACK_CALLBACK_DATA,
    CATEGORY_CUSTOM_LABEL,
    CATEGORY_SKIP_LABEL,
    CB_ASSIGN_ACCEPT_PREFIX,
    CB_ASSIGN_DECLINE_PREFIX,
    CB_CATEGORY_CUSTOM,
    CB_CATEGORY_PREFIX,
    CB_CATEGORY_SKIP,
    CB_DUE_NONE,
    CB_DUE_PREFIX,
    CB_POOL_INVITE_ACCEPT_PREFIX,
    CB_POOL_INVITE_DECLINE_PREFIX,
    CB_REPEAT_DAYS,
    CB_REPEAT_NONE,
    CB_REPEAT_WEEKDAYS,
    CB_SETTINGS_ASK_TOGGLE,
    CB_SETTINGS_DEFAULT_POOL_PREFIX,
    CB_SHARE_ACCEPT_PREFIX,
    CB_SHARE_DECLINE_PREFIX,
    CB_TASK_DELETE_PREFIX,
    CB_TASK_DONE_PREFIX,
    CB_TASK_POOL_PREFIX,
    CB_WEEKDAY_DONE,
    CB_WEEKDAY_PREFIX,
    DEADLINE_BUTTON_LABELS,
    DECLINE_BUTTON,
    MAIN_MENU_LABELS,
    POOL_NONE,
    POOL_PERSONAL_LABEL,
    REPEAT_DAYS_LABEL,
    REPEAT_NONE_LABEL,
    REPEAT_WEEKDAYS_LABEL,
    SETTINGS_ASK_OFF_TOGGLE,
    SETTINGS_ASK_ON_TOGGLE,
    TASK_DELETE_BUTTON,
    TASK_DONE_BUTTON,
    WEEKDAY_DONE_LABEL,
    WEEKDAY_NAMES,
)
from bot.enums import Messages
from bot.models import Pool


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard; labels are matched in command handlers."""
    builder = ReplyKeyboardBuilder()
    for label in MAIN_MENU_LABELS:
        builder.button(text=label)
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def task_actions_kb(task_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=TASK_DONE_BUTTON, callback_data=f"{CB_TASK_DONE_PREFIX}{task_id}"
    )
    builder.button(
        text=TASK_DELETE_BUTTON,
        callback_data=f"{CB_TASK_DELETE_PREFIX}{task_id}",
    )
    builder.adjust(2)
    return builder.as_markup()


def category_choice_kb(top: Iterable[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name in top:
        builder.button(text=name, callback_data=f"{CB_CATEGORY_PREFIX}{name}")
    builder.button(
        text=CATEGORY_CUSTOM_LABEL, callback_data=CB_CATEGORY_CUSTOM
    )
    builder.button(text=CATEGORY_SKIP_LABEL, callback_data=CB_CATEGORY_SKIP)
    builder.adjust(1)
    return builder.as_markup()


def deadline_choice_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in DEADLINE_BUTTON_LABELS.items():
        builder.button(text=label, callback_data=f"{CB_DUE_PREFIX}{key}")
    builder.button(text=Messages.DEADLINE_NONE, callback_data=CB_DUE_NONE)
    builder.button(text=BACK_BUTTON_TEXT, callback_data=BACK_CALLBACK_DATA)
    builder.adjust(3, 2, 1, 1)
    return builder.as_markup()


def repeat_choice_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=REPEAT_NONE_LABEL, callback_data=CB_REPEAT_NONE)
    builder.button(text=REPEAT_DAYS_LABEL, callback_data=CB_REPEAT_DAYS)
    builder.button(
        text=REPEAT_WEEKDAYS_LABEL, callback_data=CB_REPEAT_WEEKDAYS
    )
    builder.button(text=BACK_BUTTON_TEXT, callback_data=BACK_CALLBACK_DATA)
    builder.adjust(1)
    return builder.as_markup()


def _yes_no_kb(accept_data: str, decline_data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=ACCEPT_BUTTON, callback_data=accept_data)
    builder.button(text=DECLINE_BUTTON, callback_data=decline_data)
    builder.adjust(2)
    return builder.as_markup()


def pool_invite_confirm_kb(
    pool_id: PydanticObjectId, requester_id: int
) -> InlineKeyboardMarkup:
    return _yes_no_kb(
        f"{CB_POOL_INVITE_ACCEPT_PREFIX}{pool_id}:{requester_id}",
        f"{CB_POOL_INVITE_DECLINE_PREFIX}{pool_id}:{requester_id}",
    )


def share_confirm_kb(
    task_id: PydanticObjectId, requester_id: int
) -> InlineKeyboardMarkup:
    return _yes_no_kb(
        f"{CB_SHARE_ACCEPT_PREFIX}{task_id}:{requester_id}",
        f"{CB_SHARE_DECLINE_PREFIX}{task_id}:{requester_id}",
    )


def assign_confirm_kb(
    task_id: PydanticObjectId, requester_id: int
) -> InlineKeyboardMarkup:
    return _yes_no_kb(
        f"{CB_ASSIGN_ACCEPT_PREFIX}{task_id}:{requester_id}",
        f"{CB_ASSIGN_DECLINE_PREFIX}{task_id}:{requester_id}",
    )


def task_pool_choice_kb(pools: Iterable[Pool]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=POOL_PERSONAL_LABEL,
        callback_data=f"{CB_TASK_POOL_PREFIX}{POOL_NONE}",
    )
    for pool in pools:
        builder.button(
            text=pool.label, callback_data=f"{CB_TASK_POOL_PREFIX}{pool.id}"
        )
    builder.adjust(1)
    return builder.as_markup()


def settings_kb(
    pools: Iterable[Pool],
    default_pool_id: Optional[PydanticObjectId],
    ask_pool_on_create: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    personal_mark = "✅ " if default_pool_id is None else ""
    builder.button(
        text=f"{personal_mark}{POOL_PERSONAL_LABEL}",
        callback_data=f"{CB_SETTINGS_DEFAULT_POOL_PREFIX}{POOL_NONE}",
    )
    for pool in pools:
        mark = "✅ " if default_pool_id == pool.id else ""
        builder.button(
            text=f"{mark}{pool.label}",
            callback_data=f"{CB_SETTINGS_DEFAULT_POOL_PREFIX}{pool.id}",
        )
    toggle_label = (
        SETTINGS_ASK_OFF_TOGGLE
        if ask_pool_on_create
        else SETTINGS_ASK_ON_TOGGLE
    )
    builder.button(text=toggle_label, callback_data=CB_SETTINGS_ASK_TOGGLE)
    builder.adjust(1)
    return builder.as_markup()


def weekday_toggle_kb(selected: Iterable[int]) -> InlineKeyboardMarkup:
    """Toggle grid; selection is tracked in FSM state, not in callback_data."""
    selected_set = set(selected)
    builder = InlineKeyboardBuilder()
    for idx, name in enumerate(WEEKDAY_NAMES):
        mark = "✅ " if idx in selected_set else ""
        builder.button(
            text=f"{mark}{name}", callback_data=f"{CB_WEEKDAY_PREFIX}{idx}"
        )
    builder.button(text=WEEKDAY_DONE_LABEL, callback_data=CB_WEEKDAY_DONE)
    builder.button(text=BACK_BUTTON_TEXT, callback_data=BACK_CALLBACK_DATA)
    builder.adjust(4, 3, 1, 1)
    return builder.as_markup()
