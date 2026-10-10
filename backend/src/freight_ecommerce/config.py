from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Server-only settings. Database credentials are never part of public responses."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = Field(
        default="postgresql+psycopg://freight_local:local_demo_only@127.0.0.1:5432/freight_local",
        validation_alias="DATABASE_URL",
    )
    local_admin_key: SecretStr = Field(default="", validation_alias="LOCAL_ADMIN_KEY")
    packsenvios_webhook_secret: SecretStr = Field(
        default="", validation_alias="PACKSENVIOS_WEBHOOK_SECRET", repr=False
    )
    webhook_timestamp_format: Literal["unix_seconds"] | None = Field(
        default=None, validation_alias="PACKSENVIOS_WEBHOOK_TIMESTAMP_FORMAT"
    )
    webhook_company_id: UUID | None = Field(default=None, validation_alias="FREIGHT_COMPANY_ID")
    webhook_location_id: UUID | None = Field(default=None, validation_alias="FREIGHT_LOCATION_ID")

    @field_validator("local_admin_key")
    @classmethod
    def check_local_admin_key(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value() and len(value.get_secret_value()) < 32:
            raise ValueError("Local admin key must have at least 32 characters or be empty")
        return value
