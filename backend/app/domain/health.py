"""Pure availability rules. Only evaluated, committed cycles are samples."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from math import floor, isfinite
from statistics import fmean
from typing import Literal

Health = Literal["online", "degraded", "offline"]
Freshness = Literal["no_data", "fresh", "stale", "paused"]
Outcome = Literal["success", "failure"]
Degradation = Literal["failure_pending", "retry_recovered", "high_latency"]


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")


@dataclass(frozen=True)
class HealthState:
    health_status: Health | None = None
    consecutive_failures: int = 0
    first_failure_at: datetime | None = None
    last_checked_at: datetime | None = None


@dataclass(frozen=True)
class HealthTransition:
    state: HealthState
    degradation_reason: Degradation | None
    open_incident: bool = False
    close_incident: bool = False
    incident_started_at: datetime | None = None
    incident_detected_at: datetime | None = None


def apply_evaluated_cycle(
    state: HealthState,
    *,
    outcome: Outcome,
    started_at: datetime,
    completed_at: datetime,
    failure_threshold: int,
    attempt_count: int = 1,
    latency_ms: float | None = None,
    latency_threshold_ms: int | None = 1000,
    incident_is_open: bool = False,
) -> HealthTransition:
    """Apply RN009–RN013; caller validates job identity, version and lease first.

    `started_at` is the observed start of the evaluated execution, whereas
    detection and recovery use its completion. Excluded cycles must never call
    this function: use `interrupt_failure_sequence` instead.
    """
    _aware(started_at)
    _aware(completed_at)
    if completed_at < started_at:
        raise ValueError("cycle completion precedes start")
    if state.last_checked_at is not None and completed_at < state.last_checked_at:
        raise ValueError("cannot apply an older observation")
    if not 1 <= failure_threshold <= 10 or not 1 <= attempt_count <= 3:
        raise ValueError("invalid threshold or attempt count")
    if latency_ms is not None and (not isfinite(latency_ms) or latency_ms < 0):
        raise ValueError("latency must be finite and nonnegative")
    if state.consecutive_failures < 0:
        raise ValueError("negative failure sequence")
    if outcome == "success":
        if latency_ms is None:
            raise ValueError("an evaluated success needs a measured latency")
        reason: Degradation | None = None
        if attempt_count > 1:
            reason = "retry_recovered"
        elif latency_threshold_ms is not None and latency_ms >= latency_threshold_ms:
            reason = "high_latency"
        return HealthTransition(
            HealthState("degraded" if reason else "online", 0, None, completed_at),
            reason,
            close_incident=incident_is_open,
        )
    if outcome != "failure":
        raise ValueError("only evaluated success/failure outcomes are accepted")
    count = state.consecutive_failures + 1
    first = state.first_failure_at if state.consecutive_failures else started_at
    if first is None:
        raise ValueError("a continuing failure sequence needs its first observation")
    offline = state.health_status == "offline" or count >= failure_threshold
    opening = offline and state.health_status != "offline" and not incident_is_open
    return HealthTransition(
        HealthState("offline" if offline else "degraded", count, first, completed_at),
        None if offline else "failure_pending",
        open_incident=opening,
        incident_started_at=first if opening else None,
        incident_detected_at=completed_at if opening else None,
    )


def interrupt_failure_sequence(state: HealthState) -> HealthState:
    """RN009/RN015: a gap/pause cannot recover an offline monitor."""
    return replace(state, consecutive_failures=0, first_failure_at=None)


def freshness(
    *, now: datetime, interval_seconds: int,
    last_checked_at: datetime | None, paused: bool = False,
) -> Freshness:
    _aware(now)
    if not 60 <= interval_seconds <= 3600:
        raise ValueError("invalid monitor interval")
    if paused:
        return "paused"
    if last_checked_at is None:
        return "no_data"
    _aware(last_checked_at)
    return "stale" if (now - last_checked_at).total_seconds() > max(2 * interval_seconds, 120) else "fresh"


@dataclass(frozen=True)
class Sample:
    scheduled_at: datetime
    outcome: Outcome
    latency_ms: float | None


@dataclass(frozen=True)
class Metrics:
    success_count: int
    failure_count: int
    latency_sample_count: int
    uptime_percent: float | None
    average_latency_ms: float | None
    p95_latency_ms: float | None


def summarize_samples(samples: Iterable[Sample], *, start: datetime, end: datetime) -> Metrics:
    """RN016–RN019: [start,end), successes only for latency, continuous p95."""
    _aware(start)
    _aware(end)
    if end <= start or (end - start).total_seconds() > 30 * 86400:
        raise ValueError("metric window must be positive and at most 30 days")
    successes = failures = 0
    latencies: list[float] = []
    for sample in samples:
        _aware(sample.scheduled_at)
        if not start <= sample.scheduled_at < end:
            continue
        if sample.outcome == "failure":
            failures += 1
        elif sample.outcome == "success":
            successes += 1
            if sample.latency_ms is not None:
                if not isfinite(sample.latency_ms) or sample.latency_ms < 0:
                    raise ValueError("invalid successful latency")
                latencies.append(sample.latency_ms)
        else:
            raise ValueError("only evaluated cycles are metric samples")
    latencies.sort()
    p95 = None
    if latencies:
        position = 0.95 * (len(latencies) - 1)
        lower = floor(position)
        upper = min(lower + 1, len(latencies) - 1)
        p95 = latencies[lower] + (latencies[upper] - latencies[lower]) * (position - lower)
    evaluated = successes + failures
    return Metrics(
        successes, failures, len(latencies),
        100 * successes / evaluated if evaluated else None,
        fmean(latencies) if latencies else None, p95,
    )


@dataclass(frozen=True)
class MonitorHealth:
    health_status: Health | None
    freshness: Freshness


def aggregate_health(monitors: Iterable[MonitorHealth]) -> tuple[Health | None, bool]:
    """RN020. Call with active monitors only; paused monitors are excluded."""
    active = [monitor for monitor in monitors if monitor.freshness != "paused"]
    eligible = [monitor.health_status for monitor in active
                if monitor.freshness == "fresh" and monitor.health_status is not None]
    complete = all(monitor.freshness == "fresh" and monitor.health_status is not None for monitor in active)
    if not eligible:
        return None, complete
    for candidate in ("offline", "degraded", "online"):
        if candidate in eligible:
            return candidate, complete
    raise ValueError("invalid health status")
