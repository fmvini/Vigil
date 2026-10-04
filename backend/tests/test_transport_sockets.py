"""TLS/HTTP over real loopback sockets with test-only physical routing.

No public DNS/socket is used. Production SSRF validation is not monkeypatched.
The routing adapter below replaces PinnedNetworkBackend only for TLS wire tests;
separate tests prove the default backend refuses loopback before opening a socket.
"""

import asyncio
import socket
import ssl
from contextlib import asynccontextmanager
from pathlib import Path

import httpcore
import pytest
from test_transport import claim

from app.monitoring.executor import CheckExecutor, OperationalError
from app.monitoring.transport import (
    BlockedDestination,
    HeaderGuardStream,
    PinnedNetworkBackend,
    SafeTransport,
)

FIXTURES = Path(__file__).parent / "fixtures" / "tls"


@asynccontextmanager
async def tls_server(host):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(FIXTURES / "server.pem", FIXTURES / "server.key.pem")
    sni, requests, peers, errors = [], [], [], []
    finished = asyncio.Event()
    tasks = set()
    writers = set()

    def on_sni(ssl_socket, hostname, ssl_context):
        sni.append(hostname)

    context.set_servername_callback(on_sni)

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        writers.add(writer)
        try:
            peers.append(writer.get_extra_info("peername"))
            async with asyncio.timeout(3):
                requests.append(await reader.readuntil(b"\r\n\r\n"))
                # Large declared body with no body bytes. Executor must close after headers.
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 9999999\r\n\r\n")
                await writer.drain()
                assert await reader.read(1) == b""
        except (ConnectionError, ssl.SSLError):
            pass  # peer closing without close_notify is expected for header-only checks
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, ssl.SSLError):
                pass
            writers.discard(writer)
            tasks.discard(task)
            finished.set()

    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    server = await asyncio.start_server(
        handle, host, 0, ssl=context, family=family, ssl_handshake_timeout=2
    )
    try:
        yield server.sockets[0].getsockname()[1], sni, requests, peers, errors, finished
    finally:
        server.close()
        await server.wait_closed()
        for writer in tuple(writers):
            writer.close()
        for task in tuple(tasks):
            task.cancel()
        await asyncio.gather(*tuple(tasks), return_exceptions=True)


class LocalSocketBackend(httpcore.AsyncNetworkBackend):
    """Routes a logical HTTPS origin ONLY to the fixture's real local socket."""

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.raw = httpcore.AnyIOBackend()
        self.calls, self.streams = [], []

    async def connect_tcp(self, host, port, **kwargs):
        assert host in {"sockets.example.com", "wrong.example.com"} and port == 443
        self.calls.append((host, port))
        stream = await self.raw.connect_tcp(self.host, self.port, **kwargs)
        self.streams.append(stream)
        return HeaderGuardStream(stream)


def transport_for(backend, *, trust_test_ca):
    transport = SafeTransport(backend=backend)
    context = transport.pool._ssl_context
    if trust_test_ca:
        context.load_verify_locations(cafile=str(FIXTURES / "ca.pem"))
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    return transport


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
async def test_real_tls_sni_host_and_headers_only_over_ipv4_ipv6(host, monkeypatch):
    # No environment proxy or alternate CA may redirect the physical test socket.
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("SSL_CERT_FILE", "nonexistent-environment-ca.pem")
    async with tls_server(host) as (port, sni, requests, peers, errors, finished):
        backend = LocalSocketBackend(host, port)
        result = await CheckExecutor(
            transport_factory=lambda: transport_for(backend, trust_test_ca=True)
        ).run(claim(url="https://sockets.example.com/health", timeout_ms=2000))
        assert result.outcome == "success", result
        await asyncio.wait_for(finished.wait(), 3)
        assert result.outcome == "success" and result.attempt_count == 1
        assert sni == ["sockets.example.com"]
        assert len(requests) == 1 and b"Host: sockets.example.com\r\n" in requests[0]
        assert requests[0].startswith(b"GET /health HTTP/1.1\r\n")
        assert peers[0][0] == host and errors == []
        assert len(backend.calls) == 1


@pytest.mark.parametrize("failure", ["untrusted_ca", "wrong_hostname"])
async def test_real_tls_certificate_failure_is_final_and_never_sends_http(failure):
    async with tls_server("127.0.0.1") as (port, sni, requests, _, errors, _):
        backend = LocalSocketBackend("127.0.0.1", port)
        hostname = "wrong.example.com" if failure == "wrong_hostname" else "sockets.example.com"
        result = await CheckExecutor(
            transport_factory=lambda: transport_for(
                backend, trust_test_ca=failure == "wrong_hostname"
            )
        ).run(claim(url=f"https://{hostname}/health", timeout_ms=2000, retry_count=2))
        assert result.outcome == "failure" and result.error_code == "tls_error"
        assert result.attempt_count == 1 and len(backend.calls) == 1
        assert sni == [hostname] and requests == [] and errors == []


@pytest.mark.parametrize("answers", [["127.0.0.1"], ["::1"], ["8.8.8.8", "127.0.0.1"]])
async def test_runtime_ssrf_blocks_loopback_before_real_socket(answers):
    sockets = []

    class ObservedBackend(httpcore.AnyIOBackend):
        async def connect_tcp(self, *args, **kwargs):
            sockets.append(args)
            return await super().connect_tcp(*args, **kwargs)

    async def resolve(host, port):
        return answers

    backend = PinnedNetworkBackend(resolver=resolve, backend=ObservedBackend())
    with pytest.raises(BlockedDestination):
        await backend.connect_tcp("sockets.example.com", 443)
    assert sockets == []


async def test_default_transport_refuses_literal_loopback_without_local_adapter():
    with pytest.raises(OperationalError, match="blocked_destination"):
        await CheckExecutor().run(claim(url="https://127.0.0.1/health"))
