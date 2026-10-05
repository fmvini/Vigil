import asyncio
import io
import json
import logging
import sys
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from test_worker import SuccessExecutor, scheduled_job

from app.db.models import CheckJob, CheckResult
from app.monitoring import publisher, worker
from app.monitoring.tasks import check_task
from app.observability import (
    ActivityFormatter,
    RequestActivityMiddleware,
    configure_activity_logging,
)


@pytest.fixture
def activity_lines():
    sink = io.StringIO()
    configure_activity_logging(stream=sink)
    try:
        yield lambda: [json.loads(line) for line in sink.getvalue().splitlines()]
    finally:
        configure_activity_logging()


def test_formatter_ignores_payload_args_exception_and_unapproved_fields():
    identifier = uuid4()
    try:
        raise RuntimeError("private-exception-password")
    except RuntimeError:
        record = logging.LogRecord(
            "vigil.activity",
            logging.WARNING,
            __file__,
            1,
            "private-remote-url:%s",
            ("private-query-token",),
            sys.exc_info(),
        )
    record.job_id = identifier
    record.monitor_id = "private-email@example.com"
    record.cookie = "private-cookie"
    record.error_code = "private-remote-error"
    record.duration_ms = float("nan")
    record.attempt_count = True
    encoded = ActivityFormatter().format(record)
    assert "private" not in encoded and "NaN" not in encoded
    data = json.loads(encoded)
    assert data["event"] == "unknown_event" and data["job_id"] == str(identifier)
    assert {"monitor_id", "duration_ms", "attempt_count", "error_code"}.isdisjoint(data)


async def test_request_id_and_route_are_sanitized(authenticated, activity_lines):
    identifier = str(uuid4())
    result = await authenticated.get(
        f"/api/v1/projects/{identifier}?token=private-query-token",
        headers={"X-Request-ID": "private-client-controlled-id"},
    )
    assert result.status_code == 404
    generated = result.headers["x-request-id"]
    assert str(UUID(generated)) == generated
    events = [row for row in activity_lines() if row.get("request_id") == generated]
    assert [row["event"] for row in events] == ["request_headers", "request_finished"]
    assert all(row["route"] == "/api/v1/projects/{project_id}" for row in events)
    assert all(row["status"] == 404 and row["error_code"] == "not_found" for row in events)
    assert events[-1]["outcome"] == "complete"
    assert events[-1]["duration_ms"] >= events[0]["duration_ms"] >= 0
    assert identifier not in json.dumps(events) and "private" not in json.dumps(events)
    unknown = await authenticated.get("/private-unknown-path?token=private-secret")
    rows = [r for r in activity_lines() if r.get("request_id") == unknown.headers["x-request-id"]]
    assert all(row["route"] == "unmatched" for row in rows)


async def test_concurrent_request_contexts_do_not_share_ids(client, activity_lines):
    responses = await asyncio.gather(*(client.get("/health/live") for _ in range(20)))
    identifiers = {response.headers["x-request-id"] for response in responses}
    assert len(identifiers) == 20
    rows = activity_lines()
    for identifier in identifiers:
        pair = [row for row in rows if row.get("request_id") == identifier]
        assert [row["event"] for row in pair] == ["request_headers", "request_finished"]
        assert all(row["route"] == "/health/live" and row["status"] == 200 for row in pair)


async def test_unexpected_500_has_correlated_header_without_exception_text(api_app, activity_lines):
    @api_app.get("/qa-crash")
    async def crash():
        raise RuntimeError("private-internal-password")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app, raise_app_exceptions=False),
        base_url="https://app.test",
    ) as client:
        response = await client.get("/qa-crash")
    assert response.status_code == 500 and "private" not in response.text
    rows = [
        row for row in activity_lines() if row.get("request_id") == response.headers["x-request-id"]
    ]
    assert len(rows) == 1 and rows[0]["event"] == "request_finished"
    assert rows[0]["status"] == 500 and rows[0]["outcome"] == "error"
    assert rows[0]["error_code"] == "internal_error" and "private" not in json.dumps(rows)


async def test_stream_logs_headers_before_close_and_preserves_cancellation(activity_lines):
    started = asyncio.Event()
    messages = []
    route = SimpleNamespace(path="/events")

    async def stream(scope, receive, send):
        scope["route"] = route
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send(
            {"type": "http.response.body", "body": b"private-stream-body", "more_body": True}
        )
        started.set()
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)

    middleware = RequestActivityMiddleware(stream, route_templates={id(route): "/events"})
    task = asyncio.create_task(middleware({"type": "http", "method": "GET"}, None, send))
    await asyncio.wait_for(started.wait(), 2)
    assert [row["event"] for row in activity_lines()] == ["request_headers"]
    assert messages[1]["body"] == b"private-stream-body"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    rows = activity_lines()
    assert rows[-1]["event"] == "request_finished" and rows[-1]["outcome"] == "cancelled"
    assert rows[-1]["status"] == 200 and "private" not in json.dumps(rows)
    assert rows[0]["request_id"] == rows[-1]["request_id"]


async def test_broken_log_sink_does_not_change_response(client):
    class Broken:
        def write(self, data):
            raise OSError("sink unavailable")

    configure_activity_logging(stream=Broken())
    try:
        response = await client.get("/health/live")
        assert response.status_code == 200 and response.json() == {"status": "ok"}
    finally:
        configure_activity_logging()


async def test_job_activity_reports_commit_then_skips_duplicate(api_app, monitor, activity_lines):
    identifier = await scheduled_job(api_app, monitor)
    factory = api_app.state.session_factory
    executor = SuccessExecutor(factory)

    async def signal(event):
        assert [r for r in activity_lines() if r["event"] == "job_finalized"]
        async with factory() as db:
            assert (await db.get(CheckJob, identifier)).status == "completed"
            assert await db.scalar(select(func.count()).select_from(CheckResult)) == 1

    await worker.process_job(factory, executor, identifier, signal=signal)
    await worker.process_job(factory, executor, identifier)
    rows = [row for row in activity_lines() if row.get("job_id") == str(identifier)]
    assert [row["event"] for row in rows] == ["job_claimed", "job_finalized", "job_not_claimed"]
    assert rows[1]["outcome"] == "success" and rows[1]["attempt_count"] == 1
    assert rows[0]["start_delay_ms"] >= 0 and rows[1]["duration_ms"] >= 0
    assert executor.calls == 1


async def test_failed_finalize_never_logs_commit_or_acks(
    api_app, monitor, activity_lines, monkeypatch
):
    identifier = await scheduled_job(api_app, monitor)
    factory = api_app.state.session_factory
    original = worker.finalize_job

    async def fail(*args):
        await original(*args)
        raise RuntimeError("private-sql-parameters")

    monkeypatch.setattr(worker, "finalize_job", fail)
    acked = []

    async def ack():
        acked.append(True)

    context = SimpleNamespace(
        state=SimpleNamespace(factory=factory, executor=SuccessExecutor(factory)),
        ack=ack,
    )
    await check_task.original_func(str(identifier), context)
    rows = [row for row in activity_lines() if row.get("job_id") == str(identifier)]
    assert [row["event"] for row in rows] == ["job_claimed", "job_persistence_failed"]
    assert "private" not in json.dumps(rows) and not acked
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0
        assert (await db.get(CheckJob, identifier)).status == "running"


@pytest.mark.parametrize("failed", [False, True])
async def test_scheduler_tick_activity_is_sanitized(activity_lines, monkeypatch, failed):
    stop = asyncio.Event()

    async def schedule(factory):
        if failed:
            stop.set()
            raise RuntimeError("private-db-url")
        return [uuid4()]

    async def publish(factory, callback):
        stop.set()
        return 1

    monkeypatch.setattr(publisher, "scheduler_tick", schedule)
    monkeypatch.setattr(publisher, "publish_pending", publish)
    await publisher.scheduler_publisher_loop(None, None, stop)
    rows = activity_lines()
    assert len(rows) == 1 and "private" not in json.dumps(rows)
    assert rows[0]["event"] == ("scheduler_tick_failed" if failed else "scheduler_tick")
    if not failed:
        assert rows[0]["scheduled_count"] == rows[0]["published_count"] == 1
