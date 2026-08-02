from typing import Iterable

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

WEEKDAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

MAIN_MENU_COMMANDS = ("/new", "/list", "/share", "/assign", "/help", "/cancel")


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard; button text doubles as the command."""
    builder = ReplyKeyboardBuilder()
    for command in MAIN_MENU_COMMANDS:
        builder.button(text=command)
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def task_actions_kb(task_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово", callback_data=f"done:{task_id}")
    builder.button(text="🗑 Удалить", callback_data=f"delete:{task_id}")
    builder.adjust(2)
    return builder.as_markup()


def category_choice_kb(top: Iterable[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name in top:
        builder.button(text=name, callback_data=f"cat:{name}")
    builder.button(text="🆕 своя", callback_data="cat_custom")
    builder.button(text="⏭ без категории", callback_data="cat_skip")
    builder.adjust(1)
    return builder.as_markup()


def deadline_choice_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="15 минут", callback_data="due:15m")
    builder.button(text="1 час", callback_data="due:1h")
    builder.button(text="1 день", callback_data="due:1d")
    builder.button(text="1 неделя", callback_data="due:1w")
    builder.button(text="1 месяц", callback_data="due:1mo")
    builder.button(text="Без срока", callback_data="due_none")
    builder.adjust(3, 2, 1)
    return builder.as_markup()


def repeat_choice_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Не повторять", callback_data="repeat_none")
    builder.button(text="Через N дней", callback_data="repeat_days")
    builder.button(text="По дням недели", callback_data="repeat_weekdays")
    builder.adjust(1)
    return builder.as_markup()


def weekday_toggle_kb(selected: Iterable[int]) -> InlineKeyboardMarkup:
    """Toggle grid; selection is tracked in FSM state, not in callback_data."""
    selected_set = set(selected)
    builder = InlineKeyboardBuilder()
    for idx, name in enumerate(WEEKDAY_NAMES):
        mark = "✅ " if idx in selected_set else ""
        builder.button(text=f"{mark}{name}", callback_data=f"wd:{idx}")
    builder.button(text="Готово", callback_data="wd_done")
    builder.adjust(4, 3, 1)
    return builder.as_markup()
