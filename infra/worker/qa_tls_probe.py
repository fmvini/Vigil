"""Default pinned socket/TLS transport behind the actual worker OUTPUT policy.

Only DNS answers and the fixture CA are injected. Socket routing and peer
verification remain the production implementations, against own local aliases.
"""

import asyncio
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import egress

PUBLIC = ("93.184.216.34", "2606:4700:4700::1111")
FIXTURES = Path("/fixtures")


async def client(*, ipv6_only=None):
    sys.path.insert(0, "/app")
    from app.monitoring.executor import CheckExecutor, OperationalError
    from app.monitoring.transport import PinnedNetworkBackend, SafeTransport
    from app.security import utcnow
    from app.services.check_jobs import ClaimedJob

    assert os.getuid() == os.getgid() == 10001
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1"
    os.environ["SSL_CERT_FILE"] = "/nonexistent-environment-ca.pem"
    results = {}

    async def execute(name, answers, *, hostname="sockets.example.com", trust_ca=True):
        calls = []

        async def resolve(host, port):
            assert host == hostname and port == 443
            calls.append((host, port))
            return answers

        def transport():
            transport = SafeTransport(backend=PinnedNetworkBackend(resolver=resolve))
            context = transport.pool._ssl_context
            if trust_ca:
                context.load_verify_locations(cafile=str(FIXTURES / "ca.pem"))
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            return transport

        now = utcnow()
        claim = ClaimedJob(
            uuid4(),
            uuid4(),
            1,
            uuid4(),
            now + timedelta(seconds=60),
            now,
            now + timedelta(seconds=60),
            5000,
            {
                "url": f"https://{hostname}/health",
                "timeout_ms": 2000,
                "retry_count": 2,
                "expected_status": 200,
                "latency_threshold_ms": 1000,
            },
            now,
        )
        try:
            result = await CheckExecutor(transport_factory=transport).run(claim)
        except OperationalError as error:
            assert error.code == "blocked_destination"
            results[name] = error.code
        else:
            assert result.attempt_count == 1
            if name in {"ipv4", "ipv6"}:
                assert result.outcome == "success" and result.http_status == 200
                results[name] = "verified"
            else:
                assert result.outcome == "failure" and result.error_code == "tls_error"
                results[name] = result.error_code
        assert len(calls) == 1

    if ipv6_only is not None:
        await execute("ipv6", [ipv6_only])
    else:
        await execute("ipv4", [PUBLIC[0]])
        await execute("ipv6", [PUBLIC[1]])
        await execute("untrusted_ca", [PUBLIC[0]], trust_ca=False)
        await execute("wrong_hostname", [PUBLIC[0]], hostname="wrong.example.com")
        await execute("mixed_dns", [PUBLIC[0], "127.0.0.1"])
        await execute("private_dns", ["169.254.169.254"])
    print(json.dumps(results))


def main():
    assert re.fullmatch(r"[a-f0-9]{32}", os.environ.get("VIGIL_EGRESS_QA_TOKEN", ""))
    assert os.environ.get("VIGIL_PIPELINE_ENABLED") == "false"
    assert os.environ.get("VIGIL_MONITORING_NETWORK_ENABLED") == "false"
    if sys.argv[1:] == ["client"]:
        asyncio.run(client())
        return
    assert os.getuid() == 0
    for address in PUBLIC:
        mask = "/128" if ":" in address else "/32"
        subprocess.run(
            ["ip", "address", "add", address + mask, "dev", "lo"],
            check=True,
            capture_output=True,
        )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(FIXTURES / "server.pem", FIXTURES / "server.key.pem")
    sni, requests, closed, errors, listeners = [], [], [], [], []
    context.set_servername_callback(lambda sock, host, ctx: sni.append(host))

    def serve(listener, address):
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            connection.settimeout(3)
            try:
                with context.wrap_socket(connection, server_side=True) as secured:
                    request = b""
                    while b"\r\n\r\n" not in request:
                        chunk = secured.recv(4096)
                        assert chunk, "TLS peer closed before HTTP headers"
                        request += chunk
                        assert len(request) <= 32768
                    requests.append((address, request))
                    secured.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 9999999\r\n\r\n")
                    # No body bytes sent: successful executor must close after headers.
                    assert secured.recv(1) == b""
                    closed.append(address)
            except ssl.SSLError:
                pass  # negative certificate cases deliberately terminate TLS handshake
            except Exception as error:
                errors.append(type(error).__name__)
            finally:
                connection.close()

    try:
        for address in PUBLIC:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            listener = socket.socket(family, socket.SOCK_STREAM)
            if family == socket.AF_INET6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((address, 443))
            listener.listen(8)
            listeners.append(listener)
            threading.Thread(target=serve, args=(listener, address), daemon=True).start()
        egress.install([])
        result = subprocess.run(
            egress.dropped_command([sys.executable, str(Path(__file__).resolve()), "client"]),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert not result.stderr
        assert sni == [
            "sockets.example.com",
            "sockets.example.com",
            "sockets.example.com",
            "wrong.example.com",
        ]
        assert [address for address, request in requests] == list(PUBLIC)
        assert all(
            request.startswith(b"GET /health HTTP/1.1\r\n")
            and b"Host: sockets.example.com\r\n" in request
            for address, request in requests
        )
        assert closed == list(PUBLIC) and errors == []
        print(
            json.dumps(
                {
                    "cases": json.loads(result.stdout),
                    "http_requests": len(requests),
                    "sni_verified": True,
                    "headers_only": True,
                    "pinned_peer": "real_public_alias",
                    "uid": 10001,
                }
            )
        )
    finally:
        for listener in listeners:
            listener.close()


if __name__ == "__main__":
    main()
