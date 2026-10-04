from datetime import UTC, datetime, timedelta

import pytest

from app.domain.health import (
    HealthState,
    MonitorHealth,
    Sample,
    aggregate_health,
    apply_evaluated_cycle,
    freshness,
    interrupt_failure_sequence,
    summarize_samples,
)

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def cycle(state, outcome="failure", minute=0, **kwargs):
    return apply_evaluated_cycle(
        state, outcome=outcome, started_at=NOW + timedelta(minutes=minute),
        completed_at=NOW + timedelta(minutes=minute, seconds=1),
        failure_threshold=kwargs.pop("failure_threshold", 3), **kwargs,
    )


def test_three_failures_open_once_with_first_observation_and_detection():
    first = cycle(HealthState())
    second = cycle(first.state, minute=1)
    third = cycle(second.state, minute=2)
    fourth = cycle(third.state, minute=3, incident_is_open=True)
    assert [entry.state.health_status for entry in (first, second, third)] == ["degraded", "degraded", "offline"]
    assert third.open_incident and third.incident_started_at == NOW
    assert third.incident_detected_at == NOW + timedelta(minutes=2, seconds=1)
    assert not fourth.open_incident


def test_threshold_one_and_recovery_with_high_latency():
    failed = cycle(HealthState(), failure_threshold=1)
    assert failed.open_incident
    recovered = cycle(failed.state, "success", minute=1, latency_ms=1200, incident_is_open=True)
    assert recovered.close_incident
    assert recovered.state.health_status == "degraded"
    assert recovered.degradation_reason == "high_latency"
    assert recovered.state.consecutive_failures == 0


def test_retry_success_is_one_success_and_reason_has_priority():
    result = cycle(HealthState(), "success", attempt_count=2, latency_ms=1500)
    assert result.degradation_reason == "retry_recovered"
    metrics = summarize_samples([Sample(NOW, "success", 1500)], start=NOW, end=NOW + timedelta(days=1))
    assert metrics.success_count == 1 and metrics.uptime_percent == 100


def test_gap_breaks_sequence_but_does_not_recover_offline():
    first = cycle(HealthState(), failure_threshold=2)
    after_gap = cycle(interrupt_failure_sequence(first.state), minute=1, failure_threshold=2)
    assert after_gap.state.health_status == "degraded" and not after_gap.open_incident
    offline = HealthState("offline", 3, NOW, NOW)
    assert interrupt_failure_sequence(offline).health_status == "offline"
    still_failed = cycle(interrupt_failure_sequence(offline), minute=1, incident_is_open=True)
    assert still_failed.state.health_status == "offline" and not still_failed.close_incident


def test_latency_boundary_and_disabled_threshold():
    assert cycle(HealthState(), "success", latency_ms=1000).degradation_reason == "high_latency"
    assert cycle(HealthState(), "success", latency_ms=1000, latency_threshold_ms=None).state.health_status == "online"


def test_freshness_boundary_pause_and_missing_measurement():
    assert freshness(now=NOW, interval_seconds=60, last_checked_at=None) == "no_data"
    assert freshness(now=NOW, interval_seconds=60, last_checked_at=None, paused=True) == "paused"
    assert freshness(now=NOW, interval_seconds=60, last_checked_at=NOW - timedelta(seconds=120)) == "fresh"
    assert freshness(now=NOW, interval_seconds=60, last_checked_at=NOW - timedelta(seconds=121)) == "stale"
    assert freshness(now=NOW, interval_seconds=300, last_checked_at=NOW - timedelta(seconds=599)) == "fresh"


def test_metrics_half_open_window_uptime_and_continuous_percentile():
    samples = [Sample(NOW + timedelta(minutes=index), "success", float((index + 1) * 100)) for index in range(9)]
    samples += [Sample(NOW + timedelta(minutes=9), "failure", 99999)]
    samples += [Sample(NOW - timedelta(seconds=1), "failure", None), Sample(NOW + timedelta(days=1), "failure", None)]
    metrics = summarize_samples(samples, start=NOW, end=NOW + timedelta(days=1))
    assert metrics.uptime_percent == 90
    assert metrics.latency_sample_count == 9
    assert metrics.average_latency_ms == 500
    assert metrics.p95_latency_ms == pytest.approx(860)


def test_empty_metrics_are_null_and_project_uses_all_samples():
    empty = summarize_samples([], start=NOW, end=NOW + timedelta(days=1))
    assert empty.uptime_percent is empty.average_latency_ms is empty.p95_latency_ms is None
    # Unequal monitor populations must not average their respective uptime/p95.
    samples = [Sample(NOW, "success", 100)] * 9 + [Sample(NOW, "failure", None)]
    assert summarize_samples(samples, start=NOW, end=NOW + timedelta(days=1)).uptime_percent == 90


def test_partial_project_excludes_stale_and_paused_health():
    assert aggregate_health([MonitorHealth("online", "fresh"), MonitorHealth("offline", "stale")]) == ("online", False)
    assert aggregate_health([MonitorHealth("offline", "paused"), MonitorHealth("degraded", "fresh")]) == ("degraded", True)
    assert aggregate_health([MonitorHealth(None, "no_data")]) == (None, False)
    assert aggregate_health([]) == (None, True)


@pytest.mark.parametrize("latency", [-1, float("inf"), float("nan")])
def test_invalid_latency_never_becomes_success(latency):
    with pytest.raises(ValueError):
        cycle(HealthState(), "success", latency_ms=latency)


def test_naive_timestamp_and_old_observation_rejected():
    with pytest.raises(ValueError):
        freshness(now=NOW.replace(tzinfo=None), interval_seconds=60, last_checked_at=None)
    with pytest.raises(ValueError):
        cycle(HealthState(last_checked_at=NOW + timedelta(days=1)))
