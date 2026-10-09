"""Initial Vigil schema. Business transitions and authorization live in services."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditTimestamps, Base, UUIDPrimaryKey

TIMESTAMP = DateTime(timezone=True)
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class User(UUIDPrimaryKey, AuditTimestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email"),
        CheckConstraint(
            "email = lower(trim(email)) AND length(email) > 0", name="email_normalized"
        ),
    )
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class LegalAcceptance(UUIDPrimaryKey, Base):
    """One immutable audit entry per successful authentication operation.

    Services append entries in the user/session transaction and supply the UTC
    timestamp. No uniqueness by user/version: repeated logins retain each entry.
    """

    __tablename__ = "legal_acceptances"
    __table_args__ = (
        CheckConstraint(
            "length(trim(terms_version)) > 0 AND length(terms_version) <= 32",
            name="terms_version_nonempty",
        ),
        CheckConstraint(
            "length(trim(privacy_version)) > 0 AND length(privacy_version) <= 32",
            name="privacy_version_nonempty",
        ),
        CheckConstraint("action IN ('register', 'login')", name="action_values"),
        Index("ix_legal_acceptances_user_accepted_at", "user_id", "accepted_at"),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    terms_version: Mapped[str] = mapped_column(String(32))
    privacy_version: Mapped[str] = mapped_column(String(32))
    accepted_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    action: Mapped[str] = mapped_column(String(16))


class Session(UUIDPrimaryKey, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("token_hash"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint("last_seen_at >= created_at", name="seen_after_creation"),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at", name="revoked_after_creation"
        ),
        Index("ix_sessions_user_revoked", "user_id", "revoked_at"),
        Index("ix_sessions_expires_at", "expires_at"),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(Text)
    csrf_token: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class Project(UUIDPrimaryKey, AuditTimestamps, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("public_slug"),
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
        Index(
            "ix_projects_owner_active",
            "owner_id",
            "created_at",
            "id",
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    public_slug: Mapped[str] = mapped_column(String(80))
    public_status_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    revision: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class Monitor(UUIDPrimaryKey, AuditTimestamps, Base):
    __tablename__ = "monitors"
    __table_args__ = (
        CheckConstraint("method = 'GET'", name="method_get"),
        CheckConstraint("interval_seconds BETWEEN 60 AND 3600", name="interval_range"),
        CheckConstraint("timeout_ms BETWEEN 1000 AND 15000", name="timeout_range"),
        CheckConstraint("expected_status BETWEEN 200 AND 599", name="expected_status_range"),
        CheckConstraint("failure_threshold BETWEEN 1 AND 10", name="failure_threshold_range"),
        CheckConstraint("retry_count BETWEEN 0 AND 2", name="retry_count_range"),
        CheckConstraint(
            "latency_threshold_ms IS NULL OR (latency_threshold_ms BETWEEN 100 AND 15000 AND latency_threshold_ms <= timeout_ms)",
            name="latency_threshold_range",
        ),
        CheckConstraint(
            "(retry_count + 1) * timeout_ms + CASE retry_count WHEN 0 THEN 0 WHEN 1 THEN 600 ELSE 1800 END + 3000 <= 50000",
            name="cycle_budget",
        ),
        CheckConstraint("config_version >= 1", name="config_version_positive"),
        CheckConstraint("consecutive_failures >= 0", name="failures_nonnegative"),
        CheckConstraint(
            "health_status IN ('online', 'degraded', 'offline')", name="health_status_values"
        ),
        CheckConstraint("last_outcome IN ('success', 'failure')", name="outcome_values"),
        CheckConstraint(
            "last_degradation_reason IN ('failure_pending', 'retry_recovered', 'high_latency')",
            name="degradation_values",
        ),
        CheckConstraint(
            "last_error_code IN ('timeout', 'dns_error', 'connection_error', 'tls_error', 'unexpected_status')",
            name="error_values",
        ),
        CheckConstraint("last_http_status BETWEEN 200 AND 599", name="last_http_status_range"),
        CheckConstraint("last_latency_ms >= 0", name="last_latency_nonnegative"),
        CheckConstraint(
            "(paused_at IS NULL AND archived_at IS NULL) OR next_check_at IS NULL",
            name="inactive_unscheduled",
        ),
        Index("ix_monitors_project_created", "project_id", "created_at", "id"),
        Index(
            "ix_monitors_due",
            "next_check_at",
            "id",
            postgresql_where=text("paused_at IS NULL AND archived_at IS NULL"),
            sqlite_where=text("paused_at IS NULL AND archived_at IS NULL"),
        ),
    )
    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[str] = mapped_column(Text, default="GET", server_default=text("'GET'"))
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60, server_default=text("60"))
    timeout_ms: Mapped[int] = mapped_column(Integer, default=5000, server_default=text("5000"))
    expected_status: Mapped[int] = mapped_column(
        SmallInteger, default=200, server_default=text("200")
    )
    failure_threshold: Mapped[int] = mapped_column(
        SmallInteger, default=3, server_default=text("3")
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=1, server_default=text("1"))
    latency_threshold_ms: Mapped[int | None] = mapped_column(
        Integer().evaluates_none(), server_default=text("1000")
    )
    config_version: Mapped[int] = mapped_column(BigInteger, default=1, server_default=text("1"))
    paused_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    next_check_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    health_status: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    first_failure_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    last_checked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    last_scheduled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    last_http_status: Mapped[int | None] = mapped_column(SmallInteger)
    last_latency_ms: Mapped[float | None] = mapped_column(Double)
    last_outcome: Mapped[str | None] = mapped_column(Text)
    last_error_code: Mapped[str | None] = mapped_column(Text)
    last_degradation_reason: Mapped[str | None] = mapped_column(Text)


class CheckJob(UUIDPrimaryKey, AuditTimestamps, Base):
    __tablename__ = "check_jobs"
    __table_args__ = (
        UniqueConstraint(
            "monitor_id", "config_version", "scheduled_at", name="uq_check_jobs_cycle"
        ),
        UniqueConstraint(
            "id",
            "monitor_id",
            "config_version",
            "scheduled_at",
            name="uq_check_jobs_result_identity",
        ),
        CheckConstraint("config_version >= 1", name="config_version_positive"),
        CheckConstraint("expires_at > scheduled_at", name="expiry_after_schedule"),
        CheckConstraint("budget_ms BETWEEN 1 AND 50000", name="budget_range"),
        CheckConstraint("skipped_slots >= 0", name="skipped_nonnegative"),
        CheckConstraint("execution_count BETWEEN 0 AND 3", name="execution_count_range"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'expired', 'cancelled', 'exhausted')",
            name="status_values",
        ),
        CheckConstraint("(lease_token IS NULL) = (lease_expires_at IS NULL)", name="lease_pair"),
        CheckConstraint(
            "status != 'running' OR (lease_token IS NOT NULL AND started_at IS NOT NULL AND execution_count >= 1)",
            name="running_lease",
        ),
        CheckConstraint(
            "status IN ('pending', 'running') OR (finished_at IS NOT NULL AND lease_token IS NULL)",
            name="terminal_finished",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= scheduled_at", name="finished_after_schedule"
        ),
        Index(
            "uq_check_jobs_open_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
        Index(
            "ix_check_jobs_pending_publish",
            "retry_at",
            "published_at",
            "scheduled_at",
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index(
            "ix_check_jobs_running_lease",
            "lease_expires_at",
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
        Index(
            "ix_check_jobs_open_expiry",
            "expires_at",
            postgresql_where=text("status IN ('pending', 'running')"),
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
        Index("ix_check_jobs_monitor_schedule", "monitor_id", "scheduled_at", "id"),
        Index("ix_check_jobs_finished_at", "finished_at"),
    )
    monitor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("monitors.id"))
    config_version: Mapped[int] = mapped_column(BigInteger)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    scheduled_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    budget_ms: Mapped[int] = mapped_column(Integer)
    skipped_slots: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(Text, default="pending", server_default=text("'pending'"))
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    retry_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    execution_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    error_code: Mapped[str | None] = mapped_column(Text)


class CheckResult(UUIDPrimaryKey, Base):
    __tablename__ = "check_results"
    __table_args__ = (
        UniqueConstraint("job_id"),
        ForeignKeyConstraint(
            ["job_id", "monitor_id", "config_version", "scheduled_at"],
            [
                "check_jobs.id",
                "check_jobs.monitor_id",
                "check_jobs.config_version",
                "check_jobs.scheduled_at",
            ],
            name="fk_check_results_job_identity",
        ),
        CheckConstraint("outcome IN ('success', 'failure')", name="outcome_values"),
        CheckConstraint("health_after IN ('online', 'degraded', 'offline')", name="health_values"),
        CheckConstraint(
            "degradation_reason IN ('failure_pending', 'retry_recovered', 'high_latency')",
            name="degradation_values",
        ),
        CheckConstraint(
            "error_code IN ('timeout', 'dns_error', 'connection_error', 'tls_error', 'unexpected_status')",
            name="error_values",
        ),
        CheckConstraint("http_status BETWEEN 200 AND 599", name="http_status_range"),
        CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        CheckConstraint(
            "cycle_duration_ms >= 0 AND queue_delay_ms >= 0", name="durations_nonnegative"
        ),
        CheckConstraint("attempt_count BETWEEN 1 AND 3", name="attempt_count_range"),
        CheckConstraint(
            "scheduled_at <= started_at AND started_at <= completed_at", name="temporal_order"
        ),
        CheckConstraint(
            "outcome != 'success' OR (http_status IS NOT NULL AND latency_ms IS NOT NULL AND error_code IS NULL)",
            name="success_response",
        ),
        Index("ix_check_results_history", "monitor_id", text("scheduled_at DESC"), text("id DESC")),
        Index("ix_check_results_completed_at", "completed_at"),
    )
    job_id: Mapped[UUID] = mapped_column(Uuid)
    monitor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("monitors.id"))
    config_version: Mapped[int] = mapped_column(BigInteger)
    scheduled_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    completed_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    outcome: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    latency_ms: Mapped[float | None] = mapped_column(Double)
    cycle_duration_ms: Mapped[float] = mapped_column(Double)
    queue_delay_ms: Mapped[float] = mapped_column(Double)
    attempt_count: Mapped[int] = mapped_column(SmallInteger)
    attempts: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT)
    error_code: Mapped[str | None] = mapped_column(Text)
    health_after: Mapped[str] = mapped_column(Text)
    degradation_reason: Mapped[str | None] = mapped_column(Text)


class Incident(UUIDPrimaryKey, AuditTimestamps, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "started_at <= detected_at AND (ended_at IS NULL OR detected_at <= ended_at)",
            name="temporal_order",
        ),
        CheckConstraint("(ended_at IS NULL) = (end_reason IS NULL)", name="end_pair"),
        CheckConstraint(
            "end_reason IN ('recovered', 'configuration_changed', 'archived')",
            name="end_reason_values",
        ),
        CheckConstraint(
            "cause_code IN ('timeout', 'dns_error', 'connection_error', 'tls_error', 'unexpected_status')",
            name="cause_values",
        ),
        CheckConstraint("failure_threshold_snapshot BETWEEN 1 AND 10", name="threshold_range"),
        Index(
            "uq_incidents_open_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
            sqlite_where=text("ended_at IS NULL"),
        ),
        Index("ix_incidents_history", "monitor_id", text("started_at DESC"), text("id DESC")),
        Index("ix_incidents_ended_at", "ended_at"),
        Index(
            "ix_incidents_opening_check_id",
            "opening_check_id",
            postgresql_where=text("opening_check_id IS NOT NULL"),
            sqlite_where=text("opening_check_id IS NOT NULL"),
        ),
        Index(
            "ix_incidents_closing_check_id",
            "closing_check_id",
            postgresql_where=text("closing_check_id IS NOT NULL"),
            sqlite_where=text("closing_check_id IS NOT NULL"),
        ),
    )
    monitor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("monitors.id"))
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    detected_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    end_reason: Mapped[str | None] = mapped_column(Text)
    opening_check_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("check_results.id", ondelete="SET NULL")
    )
    closing_check_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("check_results.id", ondelete="SET NULL")
    )
    cause_code: Mapped[str] = mapped_column(Text)
    failure_threshold_snapshot: Mapped[int] = mapped_column(SmallInteger)
