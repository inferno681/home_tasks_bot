# Архитектура home-tasks-bot

Диаграммы ниже отражают код по состоянию на текущий коммит: схему двух коллекций MongoDB
(`tasks`, `users`) и путь обработки каждой команды/колбэка. При изменении моделей или хендлеров
(`bot/models.py`, `bot/handlers/*`, `bot/scheduler.py`) — обновляй и диаграммы.

## Схема данных

Mongo — документная БД без FK; связи ниже логические (через `User.user_id`), а не enforced на
уровне БД.

```mermaid
erDiagram
    USER ||--o{ TASK : "owns (user_id)"
    USER ||--o{ TASK : "assigned to (assigned_to, optional)"
    USER }o--o{ TASK : "shared with (shared_with[], optional)"

    USER {
        ObjectId id PK
        long user_id UK "Telegram user id, >32 бит, unique index"
        string username "optional"
        int utc_offset_minutes "optional, None = не спрошено"
    }

    TASK {
        ObjectId id PK
        long user_id FK "владелец, Telegram user id"
        string text "optional"
        string photo_file_id "optional"
        datetime due_at "optional, UTC"
        string status "pending | done"
        datetime created_at
        bool reminded
        long_array shared_with "user_id[], видимость + доступ к done/delete"
        string category "optional"
        long assigned_to FK "optional, user_id ответственного"
        int repeat_every_days "optional, взаимоисключимо с repeat_weekdays"
        int_array repeat_weekdays "optional, 0=Пн..6=Вс"
        datetime_array completed_history "моменты выполнения повторяющейся задачи"
    }
```

## Маршрутизация апдейтов

Один `Dispatcher` (`main.py:setup_bot_and_dispatcher`), три роутера, один outer-middleware,
работающий для polling и webhook одинаково (переключение режима — `config.service.webhook`).

```mermaid
flowchart TD
    TG[Апдейт от Telegram] --> MW["UserTrackerMiddleware<br/>(bot/middlewares.py)<br/>upsert users.user_id/username"]
    MW --> DISP{Dispatcher routers}

    DISP -->|"/start"| COMMON1[common.cmd_start]
    DISP -->|"/help"| COMMON2[common.cmd_help]
    DISP -->|"SetTimezone.waiting_offset + текст"| COMMON3[common.set_timezone]

    DISP -->|"/new, /cancel, состояния NewTask"| NEWTASK[new_task.router<br/>FSM создания задачи]

    DISP -->|"/list"| LIST1[list_tasks.cmd_list]
    DISP -->|"/share"| LIST2[list_tasks.cmd_share]
    DISP -->|"/assign"| LIST3[list_tasks.cmd_assign]
    DISP -->|"callback done:*"| LIST4[list_tasks.cb_done]
    DISP -->|"callback delete:*"| LIST5[list_tasks.cb_delete]

    SCHED["APScheduler, каждые<br/>config.scheduler.interval_seconds<br/>(bot/scheduler.py)"] -.не апдейт Telegram.-> SCHED2[check_reminders]
```

## FSM `/new` (`bot/handlers/new_task.py`)

Шаг "повторять?" показывается только если задан срок (`waiting_deadline` может уйти сразу к
созданию задачи через кнопку "Без срока" или текст "нет").

```mermaid
stateDiagram-v2
    [*] --> waiting_content: /new (после ensure_timezone)

    waiting_content --> waiting_category: текст или фото
    waiting_content --> waiting_content: другое (стикер и т.п.) — подсказка

    waiting_category --> waiting_deadline: выбрана топ-категория (cat:*)
    waiting_category --> waiting_category_custom: "🆕 своя"
    waiting_category --> waiting_deadline: "⏭ без категории"
    waiting_category_custom --> waiting_deadline: введено название

    waiting_deadline --> waiting_repeat: кнопка-шорткат due:15m/1h/1d/1w/1mo или дата ДД.ММ.ГГГГ ЧЧ:ММ
    waiting_deadline --> [*]: "Без срока" / текст "нет" → задача создана
    waiting_deadline --> waiting_deadline: невалидный ввод — подсказка

    waiting_repeat --> [*]: "Не повторять" → задача создана
    waiting_repeat --> waiting_repeat_days: "Через N дней"
    waiting_repeat_days --> [*]: введено число → задача создана

    waiting_repeat --> waiting_repeat_weekdays: "По дням недели"
    waiting_repeat_weekdays --> waiting_repeat_weekdays: toggle дня (wd:*)
    waiting_repeat_weekdays --> [*]: "Готово" (≥1 день выбран) → задача создана
```

`/cancel` (`cmd_cancel`, `StateFilter("*")`) сбрасывает FSM в `[*]` из любого состояния выше —
не показан отдельными стрелками, чтобы не дублировать каждый переход.

## `/list`, `/share`, `/assign`

Все три завязаны на общий фильтр видимости `Or(Task.user_id == uid, Task.shared_with == uid)`
(`_open_tasks_for`) — равенство скаляра с полем-массивом матчит вхождение в MongoDB.

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant B as Bot
    participant DB as MongoDB

    U->>B: /list [категория]
    B->>B: ensure_timezone (если офсет не задан — прервать и спросить)
    B->>DB: Task.find(Or(user_id==uid, shared_with==uid), status=pending[, category])
    DB-->>B: список задач
    B->>DB: User.find_one(user_id==uid) — офсет для отображения времени
    B-->>U: карточка на каждую задачу (id, категория, срок, исполнитель,<br/>правило повтора, кнопки Готово/Удалить)

    U->>B: /share id @username
    B->>DB: Task.get(id)
    alt задача не найдена или uid не владелец
        B-->>U: отказ
    else
        B->>DB: User.find_one(username==username)
        alt пользователь ещё не писал боту
            B-->>U: "пусть сначала /start"
        else
            B->>DB: task.update(AddToSet(shared_with, target.user_id))
            B-->>U: "расшарено"
        end
    end

    U->>B: /assign id @username
    Note over B,DB: то же самое, плюс Set(assigned_to = target.user_id)<br/>в одном атомарном update()
```

## Колбэки `done:*` / `delete:*`

Ключевая развилка — повторяющаяся задача не помечается `done`, а перезаряжается.

```mermaid
flowchart TD
    D0["callback done:&lt;id&gt; / delete:&lt;id&gt;"] --> GET["_get_task(id)<br/>(ловит InvalidId → None)"]
    GET --> AUTH{"task найден и<br/>_authorized(task, uid)?<br/>(владелец или shared_with)"}
    AUTH -->|нет| DENY["callback.answer('Нет доступа', alert)"]

    AUTH -->|"да, delete"| DEL["task.delete()"] --> DELOK[удалить сообщение]

    AUTH -->|"да, done"| REP{"repeat_every_days или<br/>repeat_weekdays заданы<br/>и due_at задан?"}
    REP -->|да| ROLL["next_due_date(due_at, ...)<br/>update: Set(due_at, reminded=False)<br/>+ AddToSet(completed_history, now)"]
    ROLL --> ROLLOK["Готово, повторю в следующий раз"]
    REP -->|нет| DONE["status = DONE, save()"]
    DONE --> DONEOK[убрать кнопки]
```

## Напоминания (`bot/scheduler.py`)

```mermaid
flowchart TD
    TICK["APScheduler interval tick<br/>(config.scheduler.interval_seconds)"] --> Q["Task.find(status=pending, reminded=False,<br/>due_at != None, due_at &lt;= now)"]
    Q --> LOOP{"для каждой задачи"}
    LOOP --> SEND["_send_reminder: send_photo/send_message"]
    SEND -->|успех| MARK["reminded = True, save()"] --> LOOP
    SEND -->|исключение| LOG["log warning,<br/>reminded остаётся False"] --> LOOP
    LOOP -->|конец списка| DONE([до следующего тика])
```

`due_at != None` в запросе обязателен: BSON-порядок сравнения считает `null <= date` истинным,
без этого условия задачи без срока попадали бы под фильтр `$lte`.
