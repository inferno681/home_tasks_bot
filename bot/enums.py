from enum import StrEnum, auto


class TaskStatus(StrEnum):
    PENDING = auto()
    DONE = auto()


class Messages(StrEnum):
    """User-facing bot text.

    Members are plain strings (StrEnum), usable directly wherever a str is
    expected. Members with `{placeholders}` are filled in via `.format(...)`
    at the call site.
    """

    WELCOME = (
        "Привет! Я помогу отслеживать домашние дела.\n\n"
        "/new — добавить задачу (текст, фото или оба)\n"
        "/list — список открытых задач\n"
        "/share <id задачи> <@username> — расшарить задачу\n"
        "/assign <id задачи> <@username> — назначить ответственного\n"
        "/newpool <название>, /invite, /pools, /leave — общий пул задач\n"
        "/settings — куда попадают новые задачи\n"
        "/help — помощь"
    )
    ASK_TIMEZONE = (
        "Сначала укажи свой часовой пояс как смещение от UTC (например +3 "
        "или -5) — так напоминания будут приходить вовремя. После этого "
        "повтори команду."
    )
    INVALID_OFFSET = (
        "Не понял. Пример: +3 или +5:30 или -5, в пределах -12:00..+14:00."
    )
    TIMEZONE_SAVED = "Часовой пояс сохранён."
    HELP = (
        "/new — создать задачу. Пришли текст и/или фото, затем срок "
        "(или 'нет').\n"
        "/list [категория] — открытые задачи с кнопками отметки "
        "выполнения/удаления/изменения.\n"
        "/share <id задачи> <@username> — предложить расшарить задачу (id "
        "из /list, нужно подтверждение второй стороны).\n"
        "/assign <id задачи> <@username> — предложить назначить "
        "ответственного (тоже с подтверждением).\n"
        "/newpool <название> — создать общий пул задач.\n"
        "/invite <название пула> <@username> — позвать в пул (с "
        "подтверждением второй стороны).\n"
        "/pools — список ваших пулов.\n"
        "/leave <название пула> — выйти из пула.\n"
        "/kick <название пула> <@username> — исключить из пула (только "
        "создатель).\n"
        "/settings — пул по умолчанию для новых задач, спрашивать ли его.\n"
        "/cancel — отменить текущий диалог."
    )

    NEW_TASK_PROMPT = (
        "Пришли текст, фото или фото с подписью для новой задачи.\n"
        "Можно отменить командой /cancel."
    )
    CANCELLED = "Отменено."
    INVALID_CONTENT = "Пришли текст, фото или фото с подписью."
    ASK_CATEGORY = "Есть категория? Выбери или добавь свою."
    CATEGORY_LABEL = "Категория: {category}"
    CATEGORY_CUSTOM_PROMPT = "Впиши название категории."
    CATEGORY_CUSTOM_WAITING = "Категория: своя (жду название)"
    CATEGORY_NONE = "Без категории"
    CATEGORY_TOO_LONG = (
        "Слишком длинное название (макс. {limit} байт в UTF-8), "
        "пришли покороче."
    )
    ASK_DEADLINE = (
        "Есть срок? Выбери готовый вариант, пришли дату и время в формате "
        "ДД.ММ.ГГГГ ЧЧ:ММ, или напиши 'нет'."
    )
    DEADLINE_LABEL = "Срок: {label}"
    DEADLINE_NONE = "Без срока"
    INVALID_DATE = "Не понял дату. Формат: ДД.ММ.ГГГГ ЧЧ:ММ, или 'нет'."
    DEADLINE_TEXT_HINT = (
        "Пришли дату текстом в формате ДД.ММ.ГГГГ ЧЧ:ММ, или 'нет'."
    )
    ASK_REPEAT = "Повторять задачу?"
    REPEAT_NONE = "Без повтора"
    REPEAT_DAYS_WAITING = "Повтор: через N дней (жду число)"
    ASK_REPEAT_DAYS = "Через сколько дней повторять? Пришли число."
    INVALID_REPEAT_DAYS = "Пришли положительное целое число дней."
    REPEAT_WEEKDAYS_WAITING = "Повтор: по дням недели"
    ASK_WEEKDAYS = "Выбери дни недели, потом нажми «Готово»."
    PICK_AT_LEAST_ONE_DAY = "Выбери хотя бы один день."
    REPEAT_WEEKDAYS_LABEL = "Повтор по дням: {days}"

    TASK_SAVED = "Задача сохранена."
    REMINDER_LINE = "Напомню {when}."
    CATEGORY_LINE = "Категория: {category}."
    REPEAT_DAYS_LINE = "Повтор: каждые {days} дн."
    REPEAT_WEEKDAYS_LINE = "Повтор по дням: {days}."

    NO_TEXT = "(без текста)"
    TASK_ID_LINE = "id: {task_id}"
    CATEGORY_TAG = "🏷 {category}"
    POOL_TAG = "🏠 {pool}"
    DUE_LINE = "⏰ {when}"
    ASSIGNEE_LINE = "👤 @{username}"
    REPEAT_DAYS_TAG = "🔁 каждые {days} дн."
    REPEAT_WEEKDAYS_TAG = "🔁 по дням: {days}"
    LAST_DONE_LINE = "✅ последний раз: {when}"

    NO_OPEN_TASKS = "Открытых задач нет."
    SHARE_FORMAT = "Формат: /share <id задачи из /list> <@username>"
    ASSIGN_FORMAT = "Формат: /assign <id задачи из /list> <@username>"
    TASK_NOT_FOUND = "Нет задачи с таким id. Посмотри /list."
    SHARE_OWNER_ONLY = "Делиться можно только своими задачами."
    ASSIGN_OWNER_ONLY = "Назначать можно только на своих задачах."
    USER_NOT_REGISTERED = (
        "Этот пользователь ещё не писал боту. Отправь ему ссылку — как "
        "только он нажмёт /start, придёт то же приглашение:\n{link}"
    )
    ALREADY_SHARED = "Уже расшарено."
    ASSIGN_ALREADY = "Уже назначено на этого пользователя."
    NO_ACCESS = "Нет доступа к этой задаче."
    INVITE_EXPIRED = "Приглашение больше не действительно."

    SHARE_REQUEST_SENT = "Предложение поделиться отправлено @{username}."
    SHARE_REQUEST_RECEIVED = (
        "@{username} предлагает расшарить с вами задачу «{text}»: вы "
        "сможете видеть её, отмечать выполненной и удалять. Согласны?"
    )
    SHARE_ACCEPTED = "Готово, задача теперь и у вас ✅"
    SHARE_ACCEPTED_NOTIFY = "@{username} принял(а) шеринг задачи ✅"
    SHARE_DECLINED = "Отклонено."
    SHARE_DECLINE_NOTIFY = "@{username} отклонил(а) шеринг задачи."

    ASSIGN_REQUEST_SENT = (
        "Предложение назначить ответственным отправлено @{username}."
    )
    ASSIGN_REQUEST_RECEIVED = (
        "@{username} хочет назначить вас ответственным за задачу «{text}». "
        "Согласны?"
    )
    ASSIGN_ACCEPTED = "Готово, вы назначены ответственным ✅"
    ASSIGN_ACCEPTED_NOTIFY = "@{username} принял(а) назначение ✅"
    ASSIGN_DECLINED = "Отклонено."
    ASSIGN_DECLINE_NOTIFY = "@{username} отклонил(а) назначение."
    TASK_RESCHEDULED = "Сделано! Повторю в следующий раз ✅"
    TASK_DONE = "Отмечено как сделано ✅"
    TASK_DELETED = "Удалено 🗑"

    EDIT_MENU_TITLE = "Что изменить?"
    EDIT_TEXT_PROMPT = "Пришли новый текст, фото или фото с подписью."
    TASK_TEXT_UPDATED = "Текст обновлён ✅"
    EDIT_NEEDS_DEADLINE = "Сначала укажи срок — через пункт «Срок»."
    EDIT_POOL_OWNER_ONLY = "Менять пул можно только у своих задач."

    REMINDER = "⏰ Напоминание: {text}"

    POOL_FORMAT_NEW = "Формат: /newpool <название>"
    POOL_FORMAT_INVITE = "Формат: /invite <название пула> <@username>"
    POOL_CREATED = (
        "Пул «{name}» создан (id {short_id}). Позвать кого-то: "
        "/invite {name} <@username>"
    )
    POOL_NOT_FOUND = "У вас нет такого пула. Посмотри /pools."
    POOL_AMBIGUOUS = (
        "У вас несколько пулов «{name}» — уточни, добавив id:\n{pools}"
    )
    POOL_INVITE_SENT = "Приглашение в «{pool}» отправлено @{username}."
    POOL_INVITE_RECEIVED = (
        "@{username} зовёт вас в пул задач «{pool}»: вы увидите все задачи "
        "пула, сможете отмечать их выполненными и будете получать общие "
        "напоминания. Согласны?"
    )
    POOL_ALREADY_MEMBER = "Этот пользователь уже в пуле «{pool}»."
    POOL_JOINED = "Вы в пуле «{pool}» ✅"
    POOL_JOIN_NOTIFY = "@{username} принял(а) приглашение в «{pool}» ✅"
    POOL_DECLINED = "Отклонено."
    POOL_DECLINE_NOTIFY = "@{username} отклонил(а) приглашение в «{pool}»."
    POOL_LIST_EMPTY = "У вас нет пулов. Создать: /newpool <название>"
    POOL_LIST_ITEM = "🏠 {label} ({count} чел.)"
    POOL_PERSONAL_NAME = "Мои (личные)"

    LEAVE_FORMAT = "Формат: /leave <название пула>"
    LEFT_POOL = "Вы вышли из пула «{pool}»."
    KICK_FORMAT = "Формат: /kick <название пула> <@username>"
    KICK_CREATOR_ONLY = "Исключать может только создатель пула."
    KICK_NOT_MEMBER = "Этот пользователь не в пуле «{pool}»."
    KICK_SUCCESS = "@{username} исключён(а) из «{pool}»."
    KICKED_FROM_POOL = "Вы исключены из пула «{pool}»."

    ASK_TASK_POOL = "В какой пул добавить задачу?"
    TASK_POOL_LABEL = "Пул: {pool}"

    SETTINGS_TITLE = "Настройки создания задач:"
    SETTINGS_CURRENT = (
        "Пул по умолчанию: {pool}\nСпрашивать пул при /new: {ask}"
    )
    SETTINGS_ASK_YES = "да"
    SETTINGS_ASK_NO = "нет"
    SETTINGS_DEFAULT_POOL_SAVED = "Пул по умолчанию: {pool}."
    SETTINGS_ASK_TOGGLED = "Готово."
