from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggerSettings(BaseModel):
    """Logging settings."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    format: str


class ServiceSettings(BaseModel):
    """Service settings."""

    webhook: bool
    web_server_host: str
    web_server_port: int
    webhook_path: str
    base_webhook_url: str


class MongoSettings(BaseModel):
    """MongoDB settings."""

    db: str


class SchedulerSettings(BaseModel):
    """Reminder scheduler settings."""

    interval_seconds: int


class Secrets(BaseSettings):
    """Secrets settings."""

    bot_token: SecretStr = Field(default=SecretStr(""), alias="BOT_TOKEN")
    mongo_uri: SecretStr = Field(default=SecretStr(""), alias="MONGO_URI")
    webhook_secret: SecretStr = Field(
        default=SecretStr(""), alias="WEBHOOK_SECRET"
    )

    @model_validator(mode="after")
    def check_required_secrets(self):
        """Ensure all secrets are provided via environment."""
        required = (
            ("BOT_TOKEN", self.bot_token),
            ("MONGO_URI", self.mongo_uri),
        )
        missing = [
            env_name
            for env_name, secret in required
            if not secret.get_secret_value().strip()
        ]
        if missing:
            raise ValueError(
                f"Missing required secrets: {', '.join(missing)}"
            )
        return self

    model_config = SettingsConfigDict(case_sensitive=False)


class AppConfig(BaseSettings):
    """Main configuration class."""

    service: ServiceSettings
    mongodb: MongoSettings
    scheduler: SchedulerSettings
    logger: LoggerSettings
    secrets: Secrets

    model_config = SettingsConfigDict(case_sensitive=False, extra="allow")

    @classmethod
    def load_settings(cls, file_path: str) -> "AppConfig":
        """Load configuration from YAML and environment variables."""
        yaml_config = yaml.safe_load(
            Path(file_path).read_text(encoding="utf-8")
        )
        return cls(**yaml_config, secrets=Secrets())

    @model_validator(mode="after")
    def check_webhook_requirements(self):
        """Require webhook secret and public URL when webhook mode is on."""
        if self.service.webhook:
            if not self.secrets.webhook_secret.get_secret_value().strip():
                raise ValueError(
                    "WEBHOOK_SECRET is required when service.webhook is true"
                )
            if not self.service.base_webhook_url.strip():
                raise ValueError(
                    "service.base_webhook_url is required when "
                    "service.webhook is true"
                )
        return self

    @property
    def webhook_url(self) -> str:
        """Public URL Telegram will send updates to."""
        return f"{self.service.base_webhook_url}{self.service.webhook_path}"


config = AppConfig.load_settings(
    str(Path(__file__).with_name("config.yaml"))
)
