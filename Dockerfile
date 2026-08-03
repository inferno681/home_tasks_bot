# Пины на конкретные версии, а не floating-теги (:3.12-slim, :latest) — ради
# воспроизводимости сборки; обновлять вручную по мере надобности.
FROM python:3.14.6-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local

COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-cache

# Непривилегированный пользователь — процесс бота не должен работать от root.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app

COPY --chown=app:app main.py ./
COPY --chown=app:app bot ./bot
COPY --chown=app:app config ./config

USER app

CMD ["python", "main.py"]
