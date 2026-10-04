"""Install worker-only OUTPUT policy, then irrevocably drop privileges.

Requires a dedicated Linux container/network namespace, never host networking.
Control endpoints are trusted deployment settings, not monitor destinations.
"""

import ipaddress
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

CHAIN = "VIGIL_EGRESS"
BLOCKED_V4 = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.88.99.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
)
# Allow only native IPv6 global unicast after excluding special-purpose ranges.
# Conservative: excludes public exceptions within these ranges intentionally.
BLOCKED_V6 = ("2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20")


def control_endpoints(environment, *, resolver=socket.getaddrinfo):
    endpoints = []
    for name, schemes, port in (
        ("VIGIL_DATABASE_URL", {"postgresql+asyncpg", "postgresql"}, 5432),
        ("VIGIL_REDIS_URL", {"redis", "rediss"}, 6379),
    ):
        target = urlsplit(environment.get(name, ""))
        if target.scheme not in schemes or not target.hostname or (target.port or port) != port:
            raise ValueError("Control endpoint requires its standard internal port")
        records = resolver(target.hostname, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        addresses = {entry[4][0] for entry in records}
        if not addresses or len(addresses) > 8:
            raise ValueError("Invalid control endpoint resolution")
        for value in sorted(addresses):
            address = ipaddress.ip_address(value)
            if (
                address.version != 4
                or not any(
                    address in ipaddress.ip_network(network)
                    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
                )
                or address.is_loopback
                or address.is_link_local
                or address.is_unspecified
                or address.is_multicast
                or address.is_reserved
            ):
                raise ValueError("Control endpoint must resolve only to internal IPv4")
            endpoints.append((address.compressed, port))
    return endpoints


def rules(endpoints, *, ipv6=False):
    """Ordered arguments, no shell interpolation or credential-bearing URLs."""
    result = [
        ["-N", CHAIN],
        ["-A", CHAIN, "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT"],
    ]
    if ipv6:
        # IPv6 neighbor discovery is kernel-generated, link-scoped (hop limit 255).
        # Worker has no raw-socket capability after startup.
        for kind in ("135", "136"):
            result.append(
                [
                    "-A",
                    CHAIN,
                    "-o",
                    "eth0",
                    "-p",
                    "ipv6-icmp",
                    "--icmpv6-type",
                    kind,
                    "-m",
                    "hl",
                    "--hl-eq",
                    "255",
                    "-j",
                    "ACCEPT",
                ]
            )
    if not ipv6:
        # Docker's embedded resolver only. No direct external DNS or arbitrary UDP.
        for protocol in ("udp", "tcp"):
            result.append(
                [
                    "-A",
                    CHAIN,
                    "-d",
                    "127.0.0.11/32",
                    "-p",
                    protocol,
                    "-m",
                    "conntrack",
                    "--ctorigdst",
                    "127.0.0.11",
                    "--ctorigdstport",
                    "53",
                    "--ctdir",
                    "ORIGINAL",
                    "-j",
                    "ACCEPT",
                ]
            )
        for address, port in endpoints:
            result.append(
                [
                    "-A",
                    CHAIN,
                    "-d",
                    address + "/32",
                    "-p",
                    "tcp",
                    "--dport",
                    str(port),
                    "-j",
                    "ACCEPT",
                ]
            )
    for network in BLOCKED_V6 if ipv6 else BLOCKED_V4:
        result.append(["-A", CHAIN, "-d", network, "-j", "REJECT"])
    public = ["-d", "2000::/3"] if ipv6 else []
    result.append(
        ["-A", CHAIN, *public, "-p", "tcp", "-m", "multiport", "--dports", "80,443", "-j", "ACCEPT"]
    )
    result.append(["-A", CHAIN, "-j", "REJECT"])
    # Hook only the fully constructed chain. Any failure prevents starting worker.
    result.append(["-I", "OUTPUT", "1", "-j", CHAIN])
    return result


def install(endpoints, *, run=subprocess.run):
    for executable, ipv6 in (("iptables", False), ("ip6tables", True)):
        for arguments in rules(endpoints, ipv6=ipv6):
            run([executable, "-w", "5", *arguments], check=True, capture_output=True, timeout=10)


def dropped_command(command):
    if not command:
        raise ValueError("Worker command required")
    return [
        "setpriv",
        "--reuid=10001",
        "--regid=10001",
        "--clear-groups",
        "--bounding-set=-all",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--no-new-privs",
        "--",
        *command,
    ]


def main(command=None):
    command = sys.argv[1:] if command is None else command
    try:
        if os.geteuid() != 0:
            raise ValueError("Firewall initialization requires root")
        if os.environ.get("VIGIL_WORKER_NAMESPACE") != "dedicated":
            raise ValueError("Dedicated worker namespace must be explicitly declared")
        if (
            not Path("/.dockerenv").is_file()
            or "nameserver 127.0.0.11" not in Path("/etc/resolv.conf").read_text()
        ):
            raise ValueError("Requires a Docker container on its own user-defined bridge")
        dropped = dropped_command(command)
        endpoints = control_endpoints(os.environ)
        install(endpoints)
        os.execvp(dropped[0], dropped)
    except Exception as error:
        # Never log URLs, credentials, DNS records or stderr from native commands.
        print("worker_egress_setup_failed:" + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
