from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.domain.monitors import validate_check_config, validate_url

Name = Annotated[str, Field(min_length=1, max_length=100)]
Interval = Annotated[int, Field(strict=True, ge=60, le=3600)]
Timeout = Annotated[int, Field(strict=True, ge=1000, le=15000)]
Status = Annotated[int, Field(strict=True, ge=200, le=599)]
Failures = Annotated[int, Field(strict=True, ge=1, le=10)]
Retries = Annotated[int, Field(strict=True, ge=0, le=2)]
Latency = Annotated[int, Field(strict=True, ge=100, le=15000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Credentials(Input):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(Output):
    id: UUID
    email: str
    created_at: datetime


class AuthOut(BaseModel):
    user: UserOut
    csrf_token: str


class ProjectCreate(Input):
    name: Name
    description: str | None = Field(default=None, max_length=500)
    public_status_enabled: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if value is None or not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class ProjectPatch(ProjectCreate):
    name: Name | None = None
    public_status_enabled: bool | None = None

    @model_validator(mode="after")
    def reject_null(self):
        for field in self.model_fields_set - {"description"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProjectOut(Output):
    id: UUID
    name: str
    description: str | None
    public_slug: str
    public_status_enabled: bool
    revision: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MonitorCreate(Input):
    name: Name
    url: str = Field(min_length=1, max_length=2048)
    method: Literal["GET"] = "GET"
    interval_seconds: Interval = 60
    timeout_ms: Timeout = 5000
    expected_status: Status = 200
    failure_threshold: Failures = 3
    retry_count: Retries = 1
    latency_threshold_ms: Latency | None = 1000
    is_public: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()

    @field_validator("url")
    @classmethod
    def clean_url(cls, value):
        return validate_url(value)

    @model_validator(mode="after")
    def check_budget(self):
        validate_check_config(self.model_dump())
        return self


class MonitorPatch(Input):
    name: Name | None = None
    url: str | None = Field(default=None, max_length=2048)
    method: Literal["GET"] | None = None
    interval_seconds: Interval | None = None
    timeout_ms: Timeout | None = None
    expected_status: Status | None = None
    failure_threshold: Failures | None = None
    retry_count: Retries | None = None
    latency_threshold_ms: Latency | None = None
    is_public: bool | None = None

    @model_validator(mode="after")
    def check_patch(self):
        for field in self.model_fields_set - {"latency_threshold_ms"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.name is not None:
            if not self.name.strip():
                raise ValueError("name must not be blank")
            self.name = self.name.strip()
        if self.url is not None:
            self.url = validate_url(self.url)
        return self


class MonitorOut(Output):
    id: UUID
    project_id: UUID
    name: str
    url: str
    method: Literal["GET"]
    interval_seconds: int
    timeout_ms: int
    expected_status: int
    failure_threshold: int
    retry_count: int
    latency_threshold_ms: int | None
    is_public: bool
    config_version: int
    paused_at: datetime | None
    archived_at: datetime | None
    next_check_at: datetime | None
    health_status: str | None
    consecutive_failures: int
    last_checked_at: datetime | None
    last_scheduled_at: datetime | None
    last_http_status: int | None
    last_latency_ms: float | None
    last_outcome: str | None
    last_error_code: str | None
    last_degradation_reason: str | None
    created_at: datetime
    updated_at: datetime
    is_paused: bool = False
    freshness: Literal["no_data", "fresh", "stale", "paused"] = "no_data"


class Page[T](BaseModel):
    items: list[T]
    total: int
