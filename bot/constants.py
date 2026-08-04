import re
from datetime import timedelta

# ponytail: фиксированное смещение вместо zoneinfo — не учитывает переход на
# летнее/зимнее время; апгрейд на IANA-таймзону, если это станет проблемой.
OFFSET_RE = re.compile(r"^([+-])(\d{1,2})(?::(\d{2}))?$")

MENU_NEW = "📝 Новая задача"
MENU_LIST = "📋 Список задач"
MENU_HISTORY = "📜 История"
MENU_SHARE = "🔗 Поделиться"
MENU_ASSIGN = "👤 Назначить"
MENU_POOLS = "🏠 Пулы"
MENU_SETTINGS = "⚙️ Настройки"
MENU_HELP = "❓ Помощь"
MENU_CANCEL = "✖️ Отмена"

MAIN_MENU_LABELS = (
    MENU_NEW,
    MENU_LIST,
    MENU_HISTORY,
    MENU_SHARE,
    MENU_ASSIGN,
    MENU_POOLS,
    MENU_SETTINGS,
    MENU_HELP,
    MENU_CANCEL,
)

# Sentinel для "личное" в callback_data выбора пула
# (у ObjectId такого значения быть не может).
POOL_NONE = "none"

WEEKDAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
BACK_BUTTON_TEXT = "◀️ Назад"
BACK_CALLBACK_DATA = "nav_back"

CATEGORY_CUSTOM_LABEL = "🆕 своя"
CATEGORY_SKIP_LABEL = "⏭ без категории"
REPEAT_NONE_LABEL = "Не повторять"
REPEAT_DAYS_LABEL = "Через N дней"
REPEAT_WEEKDAYS_LABEL = "По дням недели"
WEEKDAY_DONE_LABEL = "Готово"
TASK_DONE_BUTTON = "✅ Готово"
TASK_DELETE_BUTTON = "🗑 Удалить"
TASK_EDIT_BUTTON = "✏️ Изменить"
TASK_FINISH_BUTTON = "⏹ Завершить повтор"
EDIT_FIELD_TEXT_LABEL = "📝 Текст/фото"
EDIT_FIELD_CATEGORY_LABEL = "🏷 Категория"
EDIT_FIELD_DEADLINE_LABEL = "⏰ Срок"
EDIT_FIELD_REPEAT_LABEL = "🔁 Повтор"
EDIT_FIELD_POOL_LABEL = "🏠 Пул"
EDIT_CANCEL_LABEL = "✖️ Отмена"
ACCEPT_BUTTON = "✅ Принять"
DECLINE_BUTTON = "❌ Отклонить"
POOL_PERSONAL_LABEL = "🔒 Мои (личные)"
SETTINGS_ASK_ON_TOGGLE = "🔀 Спрашивать пул при создании"
SETTINGS_ASK_OFF_TOGGLE = "🔕 Не спрашивать (тихий дефолт)"
HISTORY_PREV_LABEL = "◀️"
HISTORY_NEXT_LABEL = "▶️"
HISTORY_PAGE_SIZE = 5

# --- callback_data-токены: единственный источник правды, чтобы кнопка
#     в bot/keyboards.py и фильтр в хендлере никогда не разъехались. ---
CB_CATEGORY_PREFIX = "cat:"
CB_CATEGORY_CUSTOM = "cat_custom"
CB_CATEGORY_SKIP = "cat_skip"
CB_DUE_PREFIX = "due:"
CB_DUE_NONE = "due_none"
CB_REPEAT_NONE = "repeat_none"
CB_REPEAT_DAYS = "repeat_days"
CB_REPEAT_WEEKDAYS = "repeat_weekdays"
CB_WEEKDAY_PREFIX = "wd:"
CB_WEEKDAY_DONE = "wd_done"
CB_TASK_DONE_PREFIX = "done:"
CB_TASK_DELETE_PREFIX = "delete:"
CB_TASK_FINISH_PREFIX = "finish:"
CB_TASK_EDIT_PREFIX = "edit:"
CB_EDIT_FIELD_PREFIX = "editf:"
CB_EDIT_CANCEL = "edit_cancel"

# --- Ключи полей для CB_EDIT_FIELD_PREFIX — один источник правды для меню
#     редактирования и диспетчера полей в bot/handlers/edit_task.py. ---
EDIT_FIELD_TEXT = "text"
EDIT_FIELD_CATEGORY = "category"
EDIT_FIELD_DEADLINE = "deadline"
EDIT_FIELD_REPEAT = "repeat"
EDIT_FIELD_POOL = "pool"
CB_POOL_INVITE_ACCEPT_PREFIX = "pool_yes:"
CB_POOL_INVITE_DECLINE_PREFIX = "pool_no:"
CB_SHARE_ACCEPT_PREFIX = "share_yes:"
CB_SHARE_DECLINE_PREFIX = "share_no:"
CB_ASSIGN_ACCEPT_PREFIX = "assign_yes:"
CB_ASSIGN_DECLINE_PREFIX = "assign_no:"
CB_TASK_POOL_PREFIX = "task_pool:"
CB_SETTINGS_DEFAULT_POOL_PREFIX = "set_pool:"
CB_SETTINGS_ASK_TOGGLE = "set_ask_toggle"
CB_HISTORY_PAGE_PREFIX = "hist:"

# --- /start deep-link payloads: Telegram допускает только [A-Za-z0-9_-],
#     поэтому здесь подчёркивания, а не двоеточия как в callback_data выше.
#     bot/deeplinks.py собирает/разбирает
#     "{kind}_{entity_id}_{requester_id}". ---
STARTLINK_SHARE = "share"
STARTLINK_ASSIGN = "assign"
STARTLINK_POOL = "pool"

# --- Шорткаты срока: тоже один источник правды для клавиатуры и парсинга.
#     Порядок словаря = порядок кнопок. ---
DEADLINE_SHORTCUTS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
    "1mo": timedelta(days=30),  # ponytail: приближение, не календарный месяц
}

DEADLINE_BUTTON_LABELS = {
    "15m": "15 минут",
    "1h": "1 час",
    "1d": "1 день",
    "1w": "1 неделя",
    "1mo": "1 месяц",
}

DEADLINE_CONFIRM_LABELS = {
    "15m": "через 15 минут",
    "1h": "через 1 час",
    "1d": "через 1 день",
    "1w": "через 1 неделю",
    "1mo": "через 1 месяц",
}

# Telegram ограничивает callback_data 64 байтами; категория попадает туда как
# f"{CB_CATEGORY_PREFIX}{category}" (bot/keyboards.py:category_choice_kb), и
# раз топ-категории общие на весь дом (bot/categories.py:top_categories),
# слишком длинное имя сломало бы шаг категории в /new всем, а не автору.
MAX_CATEGORY_BYTES = 50
