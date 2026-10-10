from ipaddress import ip_address
from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, StringConstraints, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from freight_ecommerce.config import ROOT
from freight_ecommerce.freight.schemas import PostalCode


class FreightSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="FREIGHT_",
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )
    mode: Literal["mock", "real"] = "mock"
    base_url: str | None = None
    api_key: SecretStr = Field(default="", repr=False)
    company_id: UUID | None = None
    location_id: UUID | None = None
    dispatch_connection_id: UUID | None = None
    origin_postal_code: PostalCode | None = None
    timeout_seconds: float = Field(default=10, gt=0, le=120)
    connect_timeout_seconds: float = Field(default=3, gt=0, le=30)
    max_attempts: int = Field(default=2, ge=1, le=3)
    max_retry_wait_seconds: float = Field(default=5, ge=0, le=60)
    mock_scenario: Literal["quoted", "unavailable", "fiscal_review"] = "quoted"
    integration_scope: Annotated[str, StringConstraints(min_length=1, max_length=128)] = (
        "local-freight"
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value):
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            port = parsed.port
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or port == 0:
                raise ValueError
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError
            if "/api/v1/freight" in unquote(parsed.path):
                raise ValueError
            if parsed.scheme == "http" and parsed.hostname != "localhost":
                if not ip_address(parsed.hostname).is_loopback:
                    raise ValueError
            if any(character.isspace() for character in value):
                raise ValueError
        except ValueError:
            raise ValueError(
                "Base URL must be an application HTTPS URL (HTTP only on loopback), "
                "without credentials, query, fragment or freight API suffix"
            ) from None
        return value.rstrip("/")

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr):
        if any(not 33 <= ord(character) <= 126 for character in value.get_secret_value()):
            raise ValueError(
                "API key must be an HTTP-safe ASCII token without whitespace or controls"
            )
        return value

    @model_validator(mode="after")
    def validate_real_configuration(self):
        key = self.api_key.get_secret_value()
        if self.base_url and key and key in unquote(self.base_url):
            raise ValueError("Credentials cannot appear in a base URL")
        if self.mode == "real" and (not self.base_url or not key or self.company_id is None):
            raise ValueError(
                "Real freight mode requires base URL, API key and configured company UUID"
            )
        return self
