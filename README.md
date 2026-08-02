# home-tasks-bot

Telegram-бот для трекинга домашних дел: текст/фото/текст+фото, дедлайны, напоминания, отметка "сделано".

## Структура

```
home-tasks-bot/
├── main.py                  # точка входа, polling или webhook (по конфигу)
├── pyproject.toml
├── setup.cfg                 # flake8/wemake, isort, mypy
├── Dockerfile
├── .dockerignore
├── .env.example
├── .github/workflows/
│   └── main.yml               # test → lint → build&push → deploy → notify
├── infra/
│   └── docker-compose-prod.yaml
├── docs/
│   └── architecture.md        # mermaid: схема БД, FSM, пути команд
├── config/
│   ├── config.py             # AppConfig: yaml-настройки + секреты из окружения
│   └── config.yaml           # несекретные настройки (имя БД, интервал шедулера)
├── tests/
│   └── test_recurrence.py    # pytest на чистую логику next_due_date
└── bot/
    ├── db.py                 # подключение к MongoDB Atlas (Beanie + PyMongo Async)
    ├── models.py              # Beanie Document Task/User
    ├── categories.py          # top_categories() — агрегация по Task.category
    ├── recurrence.py          # next_due_date() — чистая логика повторов
    ├── keyboards.py           # инлайн- и reply-клавиатуры
    ├── middlewares.py         # апдейт users.username на каждом апдейте
    ├── scheduler.py           # APScheduler, проверка дедлайнов раз в минуту
    ├── timeutils.py           # конвертация локальное время <-> UTC
    └── handlers/
        ├── common.py         # /start (+ таймзона), /help
        ├── new_task.py       # /new — FSM создания задачи (категория, срок, повтор)
        └── list_tasks.py     # /list, /share, /assign, кнопки done/delete
```

Диаграммы схемы БД и путей обработки команд — в [`docs/architecture.md`](docs/architecture.md).

## Установка

1. Создать бота через @BotFather, получить токен.
2. `uv sync` — поставит зависимости и создаст `.venv`.
3. Скопировать `.env.example` в `.env` и заполнить `BOT_TOKEN` и `MONGO_URI` (строка подключения из Atlas). Секреты читаются напрямую из переменных окружения (`pydantic-settings`, без `python-dotenv` в коде) — `.env` используется только как файл для `uv run --env-file .env`.
4. `uv run --env-file .env python main.py`

## Polling vs webhook

Режим переключается `service.webhook` в `config/config.yaml`:
- `webhook: false` (по умолчанию) — long polling, ничего дополнительно не нужно.
- `webhook: true` — поднимается aiohttp-сервер (`service.web_server_host/port`), бот регистрирует вебхук на `service.base_webhook_url + service.webhook_path` и проверяет каждый запрос по `WEBHOOK_SECRET` из `.env`. `base_webhook_url` должен быть реальным HTTPS-адресом, за который Telegram сможет достучаться (домен + реверс-прокси/туннель) — локально работает только polling. `WEBHOOK_SECRET` и `base_webhook_url` обязательны при `webhook: true` — без них конфиг не соберётся (валидация при старте).

## Как это работает

- `/new` — бот спрашивает текст/фото → категорию → срок (или "нет") → повтор (если срок задан). Задача сохраняется в коллекции `tasks`.
- `/list [категория]` — показывает все задачи со `status: pending` (опционально отфильтрованные по категории), с кнопками "Готово" и "Удалить".
- Раз в минуту `scheduler.py` ищет задачи с истёкшим `due_at` и `reminded: false`, шлёт напоминание и помечает `reminded: true`.

## Категории

Топ-3 самые используемые категории (агрегация по `Task.category` в `bot/categories.py`, без отдельной коллекции) показываются кнопками при создании задачи; можно вписать свою — она пополнит общий список для всех в доме. `/list <категория>` фильтрует по ней.

## Назначение

`/assign <id задачи из /list> <@username>` (только владелец) — одновременно назначает ответственного (`Task.assigned_to`) и даёт видимость через тот же механизм, что и `/share` (`AddToSet` в `shared_with`), одним атомарным апдейтом.

## Повторяющиеся задачи

При создании задачи со сроком можно включить повтор — "через N дней" или "по дням недели" (`bot/recurrence.py:next_due_date`, чистая функция, покрыта тестами в `tests/test_recurrence.py`). При нажатии "Готово" на повторяющейся задаче она не помечается `done`: `due_at` сдвигается на следующую дату, `reminded` сбрасывается, а момент выполнения добавляется в `Task.completed_history` — тот же документ, а не новый, история хранится прямо в нём.

## Docker / CI/CD

- `docker build -t home-tasks-bot .` — образ на `python:3.12-slim`, зависимости через `uv sync
  --no-dev` прямо в системный python (`UV_PROJECT_ENVIRONMENT=/usr/local`), рантайму нужны только
  `main.py`, `bot/`, `config/`.
- `.github/workflows/main.yml`: `test` (pytest + coverage → Codecov) и `lint` (flake8/wemake +
  isort + mypy) идут параллельно → `build_and_push_to_docker_hub` → `deploy` (SCP
  `infra/docker-compose-prod.yaml` на сервер, `docker compose pull/down/up` по SSH) → `send_message`
  (уведомление в Telegram). Пайплайн срабатывает на push в `main`.
- Нужные секреты репозитория: `DOCKERHUB_USERNAME`, `DOCKERHUB_PASSWORD`, `CONTAINER_NAME`,
  `CODECOV_TOKEN`, `HOST`, `USER`, `SSH_KEY`, `SSH_PASSPHRASE`, `PROJECT_NAME`, `TELEGRAM_TO`,
  `TELEGRAM_TOKEN` — заводятся в настройках репозитория на GitHub, в коде их нет.
- Локально: `uv run flake8 .`, `uv run isort --check-only .`, `uv run mypy .`, `uv run pytest`.

## О выборе БД-слоя

Изначально использовался `motor`, но MongoDB задепрекейтила его 14.05.2025 в пользу нативного async-API прямо в `pymongo` (`AsyncMongoClient`) — этот EOL уже наступил (14.05.2026). Поэтому проект использует `beanie` — ODM поверх `pymongo`'s `AsyncMongoClient`, даёт Pydantic-модели вместо сырых словарей (`Task.find(...)`, `task.save()`, `task.delete()` вместо ручных `insert_one`/`update_one`).

## Часовой пояс

При первом `/start` (а если его пропустили — при первом `/new` или `/list`) бот просит смещение от UTC (`+3`, `-5`, `+5:30`) и хранит его в коллекции `users` (`utc_offset_minutes`); без этого `/new`/`/list` не пускают дальше (`bot/handlers/common.py:ensure_timezone`). Ввод дедлайна конвертируется в UTC этим смещением, вывод — обратно в локальное время. Смещение фиксированное (без DST) — см. `ponytail:`-комментарий в `bot/handlers/common.py`.

## Шеринг задач

- `/share <id задачи из /list> <@username>` — расшарить свою задачу (только владелец). `/list` показывает `id` каждой задачи текстом.
- Коллекция `users` (`user_id`, `username`, `utc_offset_minutes`) пополняется middleware'ом (`bot/middlewares.py`) на каждом апдейте, чтобы `username → user_id` был свежим.
- `/list`, `done`, `delete` фильтруют по `Or(Task.user_id == uid, Task.shared_with == uid)` (равенство скаляра с полем-массивом — стандартная семантика Mongo для проверки вхождения); добавление в `shared_with` — атомарный `AddToSet`, чтобы параллельные `/share` не затирали друг друга.
