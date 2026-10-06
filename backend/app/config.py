from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIGIL_", env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://vigil:vigil@localhost:5432/vigil"
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    minimum_interval_seconds: int = Field(default=60, ge=60, le=3600)
    scheduled_checks_interval_seconds: int | None = Field(default=None, ge=1)
    database_ssl: bool = False
    database_ssl_ca_file: str | None = None
    database_schema: str | None = Field(default=None, pattern=r"^[a-z_][a-z0-9_]{0,62}$")
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=5, ge=0, le=50)
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    session_idle_seconds: int = Field(default=86400, ge=60, le=86400)
    session_absolute_seconds: int = Field(default=604800, ge=60, le=604800)
    readiness_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    pipeline_enabled: bool = False
    monitoring_network_enabled: bool = False
    redis_stream_name: str = "vigil:checks"
    redis_consumer_group: str = "vigil-workers"

    @field_validator(
        "minimum_interval_seconds",
        "scheduled_checks_interval_seconds",
        "database_pool_size",
        "database_max_overflow",
        mode="before",
    )
    @classmethod
    def integer_settings(cls, value):
        if isinstance(value, (bool, float)):
            raise ValueError("Setting must be an integer")
        return value

    @property
    def database_options(self) -> dict:
        return {
            "database_ssl": self.database_ssl,
            "database_ssl_ca_file": self.database_ssl_ca_file,
            "database_schema": self.database_schema,
            "pool_size": self.database_pool_size,
            "max_overflow": self.database_max_overflow,
        }

    @model_validator(mode="after")
    def validate_environment(self):
        if not self.database_url.startswith("postgresql+asyncpg://"):
            if not (
                self.environment == "test" and self.database_url.startswith("sqlite+aiosqlite://")
            ):
                raise ValueError("database_url must use postgresql+asyncpg")
        if not self.allowed_origins:
            raise ValueError("allowed_origins must not be empty")
        for origin in self.allowed_origins:
            try:
                parsed = urlsplit(origin)
                port = parsed.port  # urlsplit alone does not validate an explicit port.
            except ValueError:
                raise ValueError("allowed_origins must contain exact HTTP(S) origins") from None
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
                or parsed.netloc.endswith(":")
                or (port is not None and not 1 <= port <= 65535)
            ):
                raise ValueError("allowed_origins must contain exact HTTP(S) origins")
            if self.environment == "prod" and parsed.scheme != "https":
                raise ValueError("production origins require HTTPS")
        if self.environment == "prod" and "database_url" not in self.model_fields_set:
            raise ValueError("production requires an explicit database_url")
        return self

    @property
    def cookie_name(self) -> str:
        return "vigil_session" if self.environment == "dev" else "__Host-vigil_session"

    @property
    def cookie_secure(self) -> bool:
        return self.environment != "dev"
