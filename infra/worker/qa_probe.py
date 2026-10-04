"""Physical socket probe in an exclusive, externally isolated QA namespace."""

import json
import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path

import egress

PUBLIC4, PUBLIC6 = "93.184.216.34", "2606:4700:4700::1111"
PG, REDIS = "192.168.240.11", "192.168.240.12"
ALLOWED = [(PUBLIC4, 80), (PUBLIC4, 443), (PUBLIC6, 80), (PUBLIC6, 443), (PG, 5432), (REDIS, 6379)]
BLOCKED = [
    ("127.0.0.1", 80),
    ("10.123.45.67", 80),
    ("169.254.169.254", 80),
    ("100.64.12.34", 80),
    ("203.0.113.7", 80),
    (PG, 80),
    (PG, 5433),
    (REDIS, 80),
    (REDIS, 6380),
    (PUBLIC4, 8080),
    ("::1", 80),
    ("fd00:1234::1", 80),
    ("2001:db8::1", 80),
    ("2002:0808:0808::1", 80),
    ("64:ff9b::808:808", 80),
    ("3fff::1", 80),
    (PUBLIC6, 8080),
]


def connect(address, port):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        connection.connect((address, port))
        connection.sendall(b"probe")
        assert connection.recv(32) == b"vigil-egress-qa"


def client():
    assert os.getuid() == os.getgid() == 10001
    status = Path("/proc/self/status").read_text()
    capabilities = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    for field in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        assert int(capabilities[field].strip(), 16) == 0, field
    assert capabilities["NoNewPrivs"].strip() == "1"
    assert subprocess.run(["iptables", "-F"], capture_output=True).returncode != 0
    try:
        raw = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except PermissionError:
        pass
    else:
        raw.close()
        raise AssertionError("Worker retained raw socket privileges")
    allowed = []
    for target in ALLOWED:
        connect(*target)
        allowed.append(list(target))
    for target in BLOCKED:
        try:
            connect(*target)
        except OSError:
            pass
        else:
            raise AssertionError("Forbidden socket reached its live QA listener")
    # Mapped IPv6 is physically filtered by IPv4, without relying on app policy.
    try:
        connect("::ffff:127.0.0.1", 80)
    except OSError:
        pass
    else:
        raise AssertionError("IPv4-mapped loopback bypassed policy")
    assert socket.getaddrinfo(os.environ["VIGIL_QA_CONTAINER"], 80, type=socket.SOCK_STREAM)
    print(
        json.dumps(
            {
                "allowed": allowed,
                "blocked": len(BLOCKED) + 1,
                "uid": os.getuid(),
                "capabilities": 0,
                "dns": "internal_resolved",
            }
        )
    )


def main():
    assert re.fullmatch(r"[a-f0-9]{32}", os.environ.get("VIGIL_EGRESS_QA_TOKEN", ""))
    assert os.environ.get("VIGIL_PIPELINE_ENABLED") == "false"
    assert os.environ.get("VIGIL_MONITORING_NETWORK_ENABLED") == "false"
    if sys.argv[1:] == ["client"]:
        client()
        return
    assert os.getuid() == 0
    addresses = {address for address, _ in ALLOWED + BLOCKED} - {"127.0.0.1", "::1"}
    for address in sorted(addresses):
        mask = "/128" if ":" in address else "/32"
        subprocess.run(
            ["ip", "address", "add", address + mask, "dev", "lo"], check=True, capture_output=True
        )
    listeners, counts, lock = [], {}, threading.Lock()

    def serve(listener, target):
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                connection.settimeout(2)
                try:
                    if connection.recv(32) == b"probe":
                        with lock:
                            counts[target] += 1
                        connection.sendall(b"vigil-egress-qa")
                except OSError:
                    pass

    try:
        for target in ALLOWED + BLOCKED:
            family = socket.AF_INET6 if ":" in target[0] else socket.AF_INET
            listener = socket.socket(family, socket.SOCK_STREAM)
            if family == socket.AF_INET6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind(target)
            listener.listen(8)
            listeners.append(listener)
            counts[target] = 0
            threading.Thread(target=serve, args=(listener, target), daemon=True).start()
        # Prove every negative target has a live listener before installing rules.
        for target in ALLOWED + BLOCKED:
            connect(*target)
        baseline = dict(counts)
        egress.install([(PG, 5432), (REDIS, 6379)])
        result = subprocess.run(
            egress.dropped_command([sys.executable, str(Path(__file__).resolve()), "client"]),
            capture_output=True,
            text=True,
            timeout=40,
        )
        assert result.returncode == 0, result.stderr
        assert not result.stderr
        for target in BLOCKED:
            assert counts[target] == baseline[target], "Blocked listener received a probe"
        for target in ALLOWED:
            assert counts[target] == baseline[target] + 1
        report = json.loads(result.stdout)
        report["live_negative_controls"] = len(BLOCKED)
        report["firewall"] = "iptables-nft+ip6tables-nft"
        print(json.dumps(report))
    finally:
        for listener in listeners:
            listener.close()


if __name__ == "__main__":
    main()
