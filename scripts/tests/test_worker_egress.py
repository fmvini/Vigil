"""Fail-closed setup and exclusive-resource cleanup; kernel proof is opt-in tooling."""

import importlib.util
import json
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


egress = load("worker_egress", ROOT / "infra" / "worker" / "egress.py")
checker = load("egress_check", ROOT / "scripts" / "egress_check.py")
ENVIRONMENT = {
    "VIGIL_DATABASE_URL": "postgresql+asyncpg://private:secret@postgres:5432/vigil",
    "VIGIL_REDIS_URL": "redis://redis:6379/0",
}


def resolve(addresses):
    return lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, args[1])) for address in addresses
    ]


@pytest.mark.parametrize(
    "addresses",
    [
        [],
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["8.8.8.8"],
        ["::1"],
        ["fd00::1"],
        ["192.0.2.1"],
        ["172.18.0.2", "8.8.8.8"],
        ["172.18.0." + str(i) for i in range(1, 10)],
    ],
)
def test_worker_control_resolution_refuses_entire_mixed_or_unsafe_answer(addresses):
    with pytest.raises(ValueError):
        egress.control_endpoints(ENVIRONMENT, resolver=resolve(addresses))


@pytest.mark.parametrize(
    "name,value",
    [
        ("VIGIL_DATABASE_URL", "postgresql+asyncpg://db:80/vigil"),
        ("VIGIL_DATABASE_URL", "http://db:5432/vigil"),
        ("VIGIL_DATABASE_URL", ""),
        ("VIGIL_REDIS_URL", "redis://redis:443/0"),
        ("VIGIL_REDIS_URL", "file:///tmp/socket"),
    ],
)
def test_worker_control_url_refused_before_dns(name, value):
    def unexpected(*args, **kwargs):
        raise AssertionError("Unsafe URL reached DNS")

    # Database validation occurs before Redis; allow its safe literal resolution.
    resolver = resolve(["172.18.0.2"]) if name == "VIGIL_REDIS_URL" else unexpected
    with pytest.raises(ValueError):
        egress.control_endpoints({**ENVIRONMENT, name: value}, resolver=resolver)


def test_worker_exact_control_exemptions_and_both_address_families():
    endpoints = egress.control_endpoints(ENVIRONMENT, resolver=resolve(["172.18.0.2"]))
    assert endpoints == [("172.18.0.2", 5432), ("172.18.0.2", 6379)]
    recorded = []
    egress.install(endpoints, run=lambda args, **kwargs: recorded.append(args))
    assert {args[0] for args in recorded} == {"iptables", "ip6tables"}
    for family in ("iptables", "ip6tables"):
        commands = [args[3:] for args in recorded if args[0] == family]
        assert commands[-1] == ["-I", "OUTPUT", "1", "-j", egress.CHAIN]
        assert commands[-2] == ["-A", egress.CHAIN, "-j", "REJECT"]
    v4 = egress.rules(endpoints)
    control = next(i for i, rule in enumerate(v4) if "5432" in rule)
    private = next(i for i, rule in enumerate(v4) if "172.16.0.0/12" in rule)
    assert control < private
    dns = [rule for rule in v4 if "--ctorigdstport" in rule]
    assert len(dns) == 2 and all("53" in rule and "127.0.0.11" in rule for rule in dns)


def test_worker_setup_failure_prevents_exec_and_sanitizes_secrets(monkeypatch, capsys):
    monkeypatch.setattr(egress.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setenv("VIGIL_WORKER_NAMESPACE", "dedicated")
    monkeypatch.setattr(egress.Path, "is_file", lambda self: True)
    monkeypatch.setattr(egress.Path, "read_text", lambda self: "nameserver 127.0.0.11\n")
    monkeypatch.setattr(egress, "control_endpoints", lambda env: [])
    monkeypatch.setattr(
        egress.os, "execvp", lambda *args: pytest.fail("Worker started without firewall")
    )

    def failure(*args):
        raise subprocess.CalledProcessError(1, "iptables", stderr="private password URL")

    monkeypatch.setattr(egress, "install", failure)
    assert egress.main(["taskiq", "worker"]) == 1
    assert capsys.readouterr().err == "worker_egress_setup_failed:CalledProcessError\n"


def test_worker_host_network_or_missing_docker_guard_never_installs(monkeypatch):
    monkeypatch.setattr(egress.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setenv("VIGIL_WORKER_NAMESPACE", "dedicated")
    monkeypatch.setattr(egress.Path, "is_file", lambda self: True)
    monkeypatch.setattr(egress.Path, "read_text", lambda self: "nameserver 8.8.8.8\n")
    monkeypatch.setattr(egress, "install", lambda *args: pytest.fail("Host policy touched"))
    assert egress.main(["taskiq", "worker"]) == 1


class FakeDocker:
    def __init__(self, *, run_failure=False, foreign=False, unexpected_endpoint=False):
        self.calls = []
        self.runs = 0
        self.token = None
        self.run_failure, self.foreign = run_failure, foreign
        self.unexpected_endpoint = unexpected_endpoint

    def command(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ("network", "create"):
            self.token = args[-2].split("=", 1)[1]
        if args[0] == "run":
            self.runs += 1
            if self.run_failure:
                raise subprocess.TimeoutExpired("docker", 50)
            if self.runs == 1:
                return json.dumps(
                    {
                        "allowed": [1] * 6,
                        "blocked": 18,
                        "uid": 10001,
                        "capabilities": 0,
                        "dns": "internal_resolved",
                    }
                )
            return "entrypoint_dropped"
        if args[:2] == ("container", "ls"):
            return "vigil-egress-probe-" + self.token if self.run_failure else ""
        return ""

    def inspect(self, kind, name):
        label = "foreign" if self.foreign else self.token
        if kind == "container":
            return {"Config": {"Labels": {"vigil.qa.token": label}}}
        return {
            "Labels": {"vigil.qa.token": label},
            "Internal": True,
            "EnableIPv6": True,
            "Containers": {"foreign": {}} if self.unexpected_endpoint else {},
        }


def test_physical_probe_requires_successful_cleanup_and_entrypoint():
    docker = FakeDocker()
    report = checker.probe(docker)
    assert report["success"] and report["cleanup"] == "confirmed"
    assert docker.runs == 2
    assert ("network", "rm", report["network"]) in docker.calls


def test_timeout_cleans_only_own_labeled_container_then_network():
    docker = FakeDocker(run_failure=True)
    report = checker.probe(docker)
    assert not report["success"] and report["cleanup"] == "confirmed"
    assert ("container", "rm", "--force", report["container"]) in docker.calls
    assert ("network", "rm", report["network"]) in docker.calls


@pytest.mark.parametrize(
    "case", [{"run_failure": True, "foreign": True}, {"unexpected_endpoint": True}]
)
def test_unowned_resources_are_never_removed_and_cleanup_is_pending(case):
    docker = FakeDocker(**case)
    report = checker.probe(docker)
    assert not report["success"] and report["cleanup"] == "pending_review"
    assert not any(args[:2] in (("container", "rm"), ("network", "rm")) for args in docker.calls)
