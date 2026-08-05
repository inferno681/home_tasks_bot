import pytest
from pydantic import ValidationError

from config.config import (
    AppConfig,
    FSMSettings,
    LoggerSettings,
    MongoSettings,
    RedisSettings,
    SchedulerSettings,
    Secrets,
    ServiceSettings,
)


def _service(
    webhook: bool = False, base_webhook_url: str = ""
) -> ServiceSettings:
    return ServiceSettings(
        webhook=webhook,
        web_server_host="0.0.0.0",
        web_server_port=8000,
        webhook_path="/webhook",
        base_webhook_url=base_webhook_url,
    )


def _app_config(secrets: Secrets, **service_kwargs) -> AppConfig:
    return AppConfig(
        service=_service(**service_kwargs),
        mongodb=MongoSettings(db="home_tasks"),
        scheduler=SchedulerSettings(interval_seconds=60),
        fsm=FSMSettings(storage="memory", mongo_collection="fsm_states"),
        redis=RedisSettings(host="localhost", port=6379, db=0),
        logger=LoggerSettings(level="INFO", format="%(message)s"),
        secrets=secrets,
    )


def test_secrets_requires_bot_token_and_mongo_uri(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("MONGO_URI", raising=False)
    with pytest.raises(ValidationError):
        Secrets()


def test_secrets_ok_with_required_env_vars(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    secrets = Secrets()
    assert secrets.bot_token.get_secret_value() == "token"
    assert secrets.mongo_uri.get_secret_value() == "mongodb://x"
    assert secrets.webhook_secret.get_secret_value() == ""


def test_webhook_requires_secret(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    secrets = Secrets()
    with pytest.raises(ValidationError):
        _app_config(secrets, webhook=True, base_webhook_url="https://x/")


def test_webhook_requires_base_url_even_with_secret(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
    secrets = Secrets()
    with pytest.raises(ValidationError):
        _app_config(secrets, webhook=True, base_webhook_url="")


def test_webhook_ok_with_secret_and_base_url(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
    secrets = Secrets()
    config = _app_config(secrets, webhook=True, base_webhook_url="https://x")
    assert config.webhook_url == "https://x/webhook"


def test_polling_mode_does_not_require_webhook_secret(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    secrets = Secrets()
    config = _app_config(secrets, webhook=False)
    assert config.service.webhook is False


def test_redis_url_without_password(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    config = _app_config(Secrets())
    assert config.redis_url == "redis://localhost:6379/0"


def test_redis_url_with_password(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
    config = _app_config(Secrets())
    assert config.redis_url == "redis://:s3cret@localhost:6379/0"


def test_fsm_storage_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    with pytest.raises(ValidationError):
        FSMSettings(storage="postgres", mongo_collection="fsm_states")


def test_admin_id_defaults_to_none(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    monkeypatch.delenv("ADMIN_ID", raising=False)
    assert Secrets().admin_id is None


def test_admin_id_parses_from_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    monkeypatch.setenv("ADMIN_ID", "12345")
    assert Secrets().admin_id == 12345
