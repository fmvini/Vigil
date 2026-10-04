import asyncio
import ssl
from collections import deque
from datetime import timedelta
from uuid import uuid4

import httpcore
import httpx
import pytest

from app.monitoring.executor import CheckExecutor, ConcurrencyLimits, OperationalError
from app.monitoring.transport import (
    BlockedDestination,
    HeaderGuardStream,
    PinnedNetworkBackend,
    SafeTransport,
    public_address,
)
from app.security import utcnow
from app.services.check_jobs import ClaimedJob


class FakeStream(httpcore.AsyncNetworkStream):
    def __init__(self, chunks, peer):
        self.chunks = deque(chunks)
        self.peer = peer
        self.written = []
        self.reads = 0
        self.closed = False
        self.tls = []

    async def read(self, max_bytes, timeout=None):
        self.reads += 1
        if not self.chunks:
            raise AssertionError("Body must never be read")
        data = self.chunks.popleft()
        if len(data) > max_bytes:
            self.chunks.appendleft(data[max_bytes:])
        return data[:max_bytes]

    async def write(self, buffer, timeout=None):
        self.written.append(buffer)

    async def aclose(self):
        self.closed = True

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.tls.append((ssl_context, server_hostname))
        return self

    def get_extra_info(self, info):
        return self.peer if info == "server_addr" else None


class FakeBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, responses, *, peer_override=None):
        self.responses = deque(responses)
        self.calls = []
        self.streams = []
        self.peer_override = peer_override

    async def connect_tcp(self, host, port, **kwargs):
        self.calls.append((host, port))
        stream = FakeStream(self.responses.popleft(), self.peer_override or (host, port))
        self.streams.append(stream)
        return stream


def claim(**config_overrides):
    now = utcnow()
    config = dict(
        url="https://example.com/health",
        method="GET",
        interval_seconds=60,
        timeout_ms=1000,
        retry_count=1,
        expected_status=200,
        failure_threshold=3,
        latency_threshold_ms=1000,
    )
    config.update(config_overrides)
    return ClaimedJob(
        uuid4(),
        uuid4(),
        1,
        uuid4(),
        now + timedelta(seconds=60),
        now,
        now + timedelta(seconds=60),
        50000,
        config,
        now,
    )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "240.0.0.1",
        "100.64.0.1",
        "192.0.2.1",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "::ffff:8.8.8.8",
        "2002:0808:0808::1",
        "64:ff9b::a00:1",
        "2001:db8::1",
        "fe80::1%eth0",
    ],
)
def test_special_ip_ranges_are_blocked(address):
    with pytest.raises(BlockedDestination):
        public_address(address)


@pytest.mark.parametrize(
    "addresses", [["8.8.8.8", "127.0.0.1"], ["2606:4700:4700::1111", "fe80::1"], []]
)
async def test_all_dns_answers_validated_before_socket(addresses):
    async def resolver(host, port):
        return addresses

    raw = FakeBackend([])
    pinned = PinnedNetworkBackend(resolver=resolver, backend=raw)
    with pytest.raises(BlockedDestination):
        await pinned.connect_tcp("example.com", 443)
    assert raw.calls == []


@pytest.mark.parametrize("ip", ["8.8.8.8", "2606:4700:4700::1111"])
async def test_pins_ip_preserves_host_and_tls_sni_without_body(ip, monkeypatch):
    resolved = []

    async def resolver(host, port):
        resolved.append((host, port))
        return [ip]

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    monkeypatch.setenv("SSL_CERT_FILE", "nonexistent-env-ca")
    raw = FakeBackend(
        [[b"HTTP/1.1 200 OK\r\nContent-Length: 9999999\r\n\r\n", b"body-must-not-be-read"]]
    )
    pinned = PinnedNetworkBackend(resolver=resolver, backend=raw)
    result = await CheckExecutor(transport_factory=lambda: SafeTransport(backend=pinned)).run(
        claim()
    )
    assert result.outcome == "success" and result.attempt_count == 1
    assert raw.calls == [(ip, 443)] and resolved == [("example.com", 443)]
    stream = raw.streams[0]
    assert stream.closed and stream.reads == 1
    wire = b"".join(stream.written)
    assert b"Host: example.com\r\n" in wire and b"GET /health HTTP/1.1" in wire
    context, sni = stream.tls[0]
    assert (
        sni == "example.com" and context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    )


async def test_rebinding_revalidates_each_attempt_and_does_not_send_second_socket():
    answers = deque([["8.8.8.8"], ["127.0.0.1"]])

    async def resolver(host, port):
        return answers.popleft()

    raw = FakeBackend([[b"HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\n\r\n"]])
    pinned = PinnedNetworkBackend(resolver=resolver, backend=raw)

    async def no_sleep(_):
        pass

    with pytest.raises(OperationalError, match="blocked_destination"):
        await CheckExecutor(
            transport_factory=lambda: SafeTransport(backend=pinned), sleep=no_sleep
        ).run(claim())
    assert len(raw.calls) == 1


async def test_peer_mismatch_is_closed_before_http():
    async def resolver(host, port):
        return ["8.8.8.8"]

    raw = FakeBackend([[]], peer_override=("1.1.1.1", 443))
    with pytest.raises(BlockedDestination):
        await PinnedNetworkBackend(resolver=resolver, backend=raw).connect_tcp("example.com", 443)
    assert raw.streams[0].closed and raw.streams[0].written == []


async def test_redirect_is_final_status_and_never_followed():
    raw = FakeBackend(
        [[b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1\r\nContent-Length: 0\r\n\r\n"]]
    )
    pinned = PinnedNetworkBackend(backend=raw)
    result = await CheckExecutor(transport_factory=lambda: SafeTransport(backend=pinned)).run(
        claim(url="https://8.8.8.8/", expected_status=302)
    )
    assert result.outcome == "success" and len(raw.calls) == 1


async def test_large_headers_are_excluded_and_connection_closed():
    raw = FakeBackend([[b"HTTP/1.1 200 OK\r\nX-Huge: " + b"x" * 40000 + b"\r\n\r\n"]])
    pinned = PinnedNetworkBackend(backend=raw)
    with pytest.raises(OperationalError, match="blocked_destination"):
        await CheckExecutor(transport_factory=lambda: SafeTransport(backend=pinned)).run(
            claim(url="https://8.8.8.8")
        )
    assert raw.streams[0].closed


async def test_interim_headers_count_towards_aggregate_limit():
    raw = FakeStream([b"HTTP/1.1 100 Continue\r\n\r\n" * 2000], ("8.8.8.8", 443))
    guard = HeaderGuardStream(raw, max_header_bytes=100)
    from app.monitoring.transport import HeaderLimitExceeded

    with pytest.raises(HeaderLimitExceeded):
        await guard.read(65536)


@pytest.mark.parametrize(
    "statuses,expected,attempts,outcome",
    [
        ([503, 200], 200, 2, "success"),
        ([503], 503, 1, "success"),
        ([404], 200, 1, "failure"),
        ([302], 200, 1, "failure"),
        ([503, 503], 200, 2, "failure"),
    ],
)
async def test_retry_status_policy_and_sanitized_summaries(statuses, expected, attempts, outcome):
    remaining = deque(statuses)
    delays = []

    async def handler(request):
        return httpx.Response(remaining.popleft(), content=b"")

    async def sleep(delay):
        delays.append(delay)

    result = await CheckExecutor(
        transport_factory=lambda: httpx.MockTransport(handler),
        sleep=sleep,
        jitter=lambda delay: delay,
    ).run(claim(expected_status=expected))
    assert result.attempt_count == attempts and result.outcome == outcome
    assert delays == ([0.5] if attempts == 2 else [])
    assert all(
        set(a) == {"http_status", "error_code", "latency_ms", "duration_ms"}
        for a in result.attempts
    )


@pytest.mark.parametrize(
    "exception,error,retries",
    [
        (httpcore.ReadTimeout, "timeout", 2),
        (httpcore.ConnectError, "connection_error", 2),
    ],
)
async def test_transient_network_failure_retries(exception, error, retries):
    async def handler(request):
        raise exception("remote-secret-error")

    async def no_sleep(_):
        pass

    result = await CheckExecutor(
        transport_factory=lambda: httpx.MockTransport(handler), sleep=no_sleep
    ).run(claim())
    assert result.error_code == error and result.attempt_count == retries
    assert "secret" not in repr(result)


async def test_tls_failure_never_retries():
    async def handler(request):
        try:
            raise ssl.SSLCertVerificationError("invalid cert")
        except ssl.SSLError as exc:
            raise httpcore.ConnectError("TLS failed") from exc

    result = await CheckExecutor(transport_factory=lambda: httpx.MockTransport(handler)).run(
        claim()
    )
    assert result.error_code == "tls_error" and result.attempt_count == 1


@pytest.mark.parametrize("transient,attempts", [(True, 2), (False, 1)])
async def test_dns_only_transient_errors_retry(transient, attempts):
    from app.monitoring.transport import DNSFailure

    async def handler(request):
        raise DNSFailure("DNS failed", transient=transient)

    async def no_sleep(_):
        pass

    result = await CheckExecutor(
        transport_factory=lambda: httpx.MockTransport(handler), sleep=no_sleep
    ).run(claim())
    assert result.error_code == "dns_error" and result.attempt_count == attempts


async def test_total_attempt_deadline_limits_slow_trickle():
    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200)

    result = await CheckExecutor(transport_factory=lambda: httpx.MockTransport(handler)).run(
        claim(timeout_ms=20, retry_count=0)
    )
    assert result.error_code == "timeout" and result.attempt_count == 1


async def test_pool_limits_are_internal_and_map_is_reclaimed():
    limits = ConcurrencyLimits(global_limit=2, host_limit=1, acquire_timeout=0.01)
    async with limits.slot("example.com"):
        with pytest.raises(OperationalError, match="pool_exhausted"):
            async with limits.slot("example.com"):
                pytest.fail("host limit bypassed")
        async with limits.slot("other.test"):
            with pytest.raises(OperationalError, match="pool_exhausted"):
                async with limits.slot("third.test"):
                    pytest.fail("global limit bypassed")
    assert limits.hosts == {}


async def test_insufficient_remaining_budget_does_not_touch_network():
    item = claim()
    from dataclasses import replace

    item = replace(item, expires_at=utcnow() + timedelta(seconds=1))
    with pytest.raises(OperationalError, match="execution_crashed"):
        await CheckExecutor(transport_factory=lambda: pytest.fail("network called")).run(item)
