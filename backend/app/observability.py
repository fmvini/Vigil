"""Bounded activity fields; never serialize requests, exceptions or SQL params."""

import asyncio
import json
import logging
import math
import sys
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

EVENTS = frozenset(
    {
        "request_headers",
        "request_finished",
        "job_not_claimed",
        "job_claimed",
        "job_finalized",
        "job_state_not_applied",
        "job_cancelled",
        "job_persistence_failed",
        "signal_failed_after_commit",
        "scheduler_tick",
        "scheduler_tick_failed",
    }
)
ERROR_CODES = frozenset(
    {
        "unauthenticated",
        "invalid_credentials",
        "validation_error",
        "origin_forbidden",
        "browser_request_required",
        "csrf_invalid",
        "json_required",
        "not_found",
        "method_not_allowed",
        "http_error",
        "conflict",
        "quota_exceeded",
        "database_unavailable",
        "not_ready",
        "internal_error",
        "sse_connection_limit",
        "sse_unavailable",
        "blocked_destination",
        "pool_exhausted",
        "execution_crashed",
        "timeout",
        "connection_error",
        "dns_error",
        "tls_error",
        "unexpected_status",
        "header_limit_exceeded",
    }
)
LOGGER = logging.getLogger("vigil.activity")


class ActivityFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "event": record.msg
            if isinstance(record.msg, str) and record.msg in EVENTS
            else "unknown_event",
            "pid": record.process,
        }
        for key in ("request_id", "job_id", "monitor_id"):
            value = getattr(record, key, None)
            try:
                if isinstance(value, (str, UUID)):
                    data[key] = str(UUID(str(value)))
            except ValueError:
                pass
        for key, allowed in (
            ("component", {"api", "worker", "scheduler"}),
            ("method", {"GET", "POST", "PATCH", "DELETE", "PUT", "HEAD", "OPTIONS", "OTHER"}),
            (
                "outcome",
                {"complete", "error", "cancelled", "success", "failure", "operational_error"},
            ),
            ("error_code", ERROR_CODES),
        ):
            value = getattr(record, key, None)
            if isinstance(value, str) and value in allowed:
                data[key] = value
        # This field comes from the middleware's declared route whitelist, not path/query.
        route = getattr(record, "route_template", None)
        if isinstance(route, str) and len(route) <= 200:
            data["route"] = route
        for key in ("status", "scheduled_count", "published_count", "attempt_count"):
            value = getattr(record, key, None)
            if type(value) is int and 0 <= value <= 1_000_000_000:
                data[key] = value
        for key in ("duration_ms", "start_delay_ms"):
            value = getattr(record, key, None)
            if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e12:
                data[key] = round(value, 3)
        return json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


class ActivityHandler(logging.Handler):
    def __init__(self, stream=None):
        super().__init__()
        self.stream = stream
        self.setFormatter(ActivityFormatter())

    def emit(self, record):
        # Default stream is resolved at emit time, also supporting temporary capture.
        try:
            stream = self.stream if self.stream is not None else sys.stderr
            stream.write(self.format(record) + "\n")
            stream.flush()
        except (OSError, ValueError):
            # A broken log sink cannot change a transaction, ACK or HTTP response.
            pass


def configure_activity_logging(*, stream=None):
    for handler in LOGGER.handlers:
        if isinstance(handler, ActivityHandler):
            handler.stream = stream
            break
    else:
        LOGGER.addHandler(ActivityHandler(stream))
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def activity(event, *, level=logging.INFO, **fields):
    LOGGER.log(level, event, extra=fields)


class RequestActivityMiddleware:
    """Pure ASGI: one request ID, header timing and final timing, including SSE."""

    def __init__(self, app, *, route_templates):
        self.app = app
        self.route_templates = dict(route_templates)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        identifier = str(uuid4())  # incoming headers are untrusted and never copied
        scope.setdefault("state", {})["request_id"] = identifier
        started = time.monotonic()
        status = None
        outcome = "complete"

        def fields():
            route = self.route_templates.get(id(scope.get("route")), "unmatched")
            method = scope.get("method")
            return {
                "component": "api",
                "request_id": identifier,
                "method": method
                if method in {"GET", "POST", "PATCH", "DELETE", "PUT", "HEAD", "OPTIONS"}
                else "OTHER",
                "route_template": route,
                "duration_ms": (time.monotonic() - started) * 1000,
                "status": status,
                "error_code": scope["state"].get("error_code"),
            }

        async def observed_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                message = {**message, "headers": [*headers, (b"x-request-id", identifier.encode())]}
            await send(message)
            if message["type"] == "http.response.start":
                activity("request_headers", **fields())

        try:
            await self.app(scope, receive, observed_send)
        except BaseException as error:
            outcome = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
            if status is None:
                status = 500
            if outcome == "error" and not scope["state"].get("error_code"):
                scope["state"]["error_code"] = "internal_error"
            raise
        finally:
            activity("request_finished", outcome=outcome, **fields())
