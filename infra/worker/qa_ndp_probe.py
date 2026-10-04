"""NDP dependency and pinned TLS between exclusively owned IPv6 namespaces."""

import asyncio
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
from pathlib import Path

import egress
import qa_tls_probe as tls


def native(*arguments):
    return subprocess.run(
        list(arguments), check=True, capture_output=True, text=True, timeout=10
    ).stdout


def unprivileged():
    assert os.getuid() == os.getgid() == 10001
    assert all(
        int(line.split(":", 1)[1], 16) == 0
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith("Cap")
    )


def serve():
    unprivileged()
    listener = socket.socket(fileno=int(os.environ["VIGIL_QA_LISTENER_FD"]))
    listener.settimeout(25)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(tls.FIXTURES / "server.pem", tls.FIXTURES / "server.key.pem")
    sni = []
    context.set_servername_callback(lambda sock, host, ctx: sni.append(host))
    print(json.dumps({"ready": True, "uid": 10001}), flush=True)
    with listener:
        connection, _ = listener.accept()
        connection.settimeout(5)
        with context.wrap_socket(connection, server_side=True) as secured:
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = secured.recv(4096)
                assert chunk and len(request) + len(chunk) <= 32768
                request += chunk
            assert request.startswith(b"GET /health HTTP/1.1\r\n")
            assert b"Host: sockets.example.com\r\n" in request
            assert sni == ["sockets.example.com"]
            secured.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 9999999\r\n\r\n")
            assert secured.recv(1) == b""
    print(
        json.dumps(
            {
                "http_requests": 1,
                "sni_verified": True,
                "headers_only": True,
                "uid": 10001,
            }
        ),
        flush=True,
    )


def child(mode):
    result = subprocess.run(
        egress.dropped_command([sys.executable, str(Path(__file__).resolve()), mode]),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0 and not result.stderr
    return json.loads(result.stdout)


def neighbor(target):
    return json.loads(native("ip", "-j", "-6", "neigh", "show", "to", target))


def flush(target):
    native("ip", "-6", "neigh", "flush", "to", target, "dev", "eth0")
    assert neighbor(target) == []


def packets(kind, action):
    lines = native("ip6tables-save", "-c").splitlines()
    return sum(
        int(re.match(r"\[(\d+):\d+\]", line)[1])
        for line in lines
        if f"--icmpv6-type {kind} " in line and line.endswith("-j " + action)
    )


def run_client(target):
    assert os.getuid() == 0
    egress.install([])
    flush(target)
    # Negative control lives only in this disposable namespace. Put DROP before
    # conntrack, so pre-existing flows cannot hide the NDP dependency.
    blocks = [
        ["-o", "eth0", "-p", "ipv6-icmp", "--icmpv6-type", kind, "-j", "DROP"]
        for kind in ("135", "136")
    ]
    for rule in blocks:
        native("ip6tables", "-w", "5", "-I", egress.CHAIN, "1", *rule)
    assert child("negative") == {"ndp_denied": "timeout"}
    denied = packets("135", "DROP")
    assert denied > 0
    before = {kind: packets(kind, "ACCEPT") for kind in ("135", "136")}
    for rule in blocks:
        native("ip6tables", "-w", "5", "-D", egress.CHAIN, *rule)
    flush(target)
    assert child("tls") == {"ipv6": "verified"}
    accepted = {kind: packets(kind, "ACCEPT") - before[kind] for kind in before}
    entries = neighbor(target)
    assert len(entries) == 1 and entries[0]["dev"] == "eth0" and entries[0].get("lladdr")
    assert any(state in {"REACHABLE", "STALE", "DELAY"} for state in entries[0]["state"])
    # Incoming solicitation can populate the neighbor cache while this kernel
    # replies with an advertisement. Both are genuine NDP, without requiring a
    # particular ordering of the two kernels' discovery timers.
    assert sum(accepted.values()) > 0
    print(
        json.dumps(
            {
                "ndp_denied": "timeout",
                "denied_solicitations": denied,
                "accepted_solicitations": accepted["135"],
                "accepted_advertisements": accepted["136"],
                "accepted_neighbor_messages": sum(accepted.values()),
                "neighbor": "resolved_on_eth0",
                "tls": "verified",
                "pinned_peer": "own_global_unicast_peer",
                "uid": 10001,
            }
        )
    )


def main():
    assert re.fullmatch(r"[a-f0-9]{32}", os.environ.get("VIGIL_EGRESS_QA_TOKEN", ""))
    assert os.environ.get("VIGIL_PIPELINE_ENABLED") == "false"
    assert os.environ.get("VIGIL_MONITORING_NETWORK_ENABLED") == "false"
    target = os.environ["VIGIL_QA_TARGET6"]
    address = ipaddress.ip_address(target)
    assert address.version == 6 and address.is_global and target.startswith("3000:")
    mode = sys.argv[1]
    if mode == "serve":
        serve()
    elif mode == "negative":
        unprivileged()
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as connection:
            connection.settimeout(1)
            try:
                connection.connect((target, 443))
            except TimeoutError:
                print(json.dumps({"ndp_denied": "timeout"}))
            else:
                raise AssertionError("TCP reached peer while NDP denied")
    elif mode == "tls":
        unprivileged()
        asyncio.run(tls.client(ipv6_only=target))
    elif mode == "peer":
        assert os.getuid() == 0
        # Address is assigned by Docker on eth0, never an alias on client loopback.
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((target, 443))
            listener.listen(1)
            subprocess.run(
                egress.dropped_command([sys.executable, str(Path(__file__).resolve()), "serve"]),
                env={**os.environ, "VIGIL_QA_LISTENER_FD": str(listener.fileno())},
                pass_fds=[listener.fileno()],
                check=True,
                timeout=35,
            )
    elif mode == "client":
        run_client(target)
    else:
        raise ValueError("Unknown QA mode")


if __name__ == "__main__":
    main()
