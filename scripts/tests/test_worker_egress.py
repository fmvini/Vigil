"""Fail-closed setup and exclusive-resource cleanup; kernel proof is opt-in tooling."""

import importlib.util
import ipaddress
import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

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
    def __init__(
        self,
        *,
        run_failure=False,
        foreign=False,
        unexpected_endpoint=False,
        tls_incomplete=False,
        not_internal=False,
        foreign_network=False,
        replaced_container=False,
    ):
        self.calls = []
        self.runs = 0
        self.token = None
        self.run_failure, self.foreign = run_failure, foreign
        self.unexpected_endpoint = unexpected_endpoint
        self.tls_incomplete = tls_incomplete
        self.not_internal, self.foreign_network = not_internal, foreign_network
        self.replaced_container, self.container_reads = replaced_container, 0

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
            if self.runs == 2:
                return "entrypoint_dropped"
            return json.dumps(
                {
                    "cases": {
                        "ipv4": "verified",
                        "ipv6": "verified",
                        "untrusted_ca": "tls_error",
                        "wrong_hostname": "tls_error",
                        "mixed_dns": "blocked_destination",
                        "private_dns": "blocked_destination",
                    },
                    "http_requests": 2,
                    "sni_verified": not self.tls_incomplete,
                    "headers_only": True,
                    "pinned_peer": "real_public_alias",
                    "uid": 10001,
                }
            )
        if args[:2] == ("container", "ls"):
            return "vigil-egress-probe-" + self.token if self.run_failure else ""
        return ""

    def inspect(self, kind, name):
        label = "foreign" if self.foreign else self.token
        if kind == "container":
            self.container_reads += 1
            return {
                "Id": name
                + ("-replacement" if self.replaced_container and self.container_reads > 1 else ""),
                "Config": {"Labels": {"vigil.qa.token": label}},
                "NetworkSettings": {
                    "Networks": {"vigil-egress-qa-" + self.token: {}}
                    | ({"shared-network": {}} if self.foreign_network else {})
                },
            }
        return {
            "Id": "vigil-egress-qa-" + self.token,
            "Labels": {"vigil.qa.token": label},
            "Internal": not self.not_internal,
            "EnableIPv6": True,
            "Containers": {"foreign": {}} if self.unexpected_endpoint else {},
        }


def test_physical_probe_requires_successful_cleanup_and_entrypoint():
    docker = FakeDocker()
    report = checker.probe(docker)
    assert report["success"] and report["cleanup"] == "confirmed"
    assert docker.runs == 3
    assert ("network", "rm", report["network"]) in docker.calls


def test_incomplete_tls_evidence_is_failure_even_with_clean_resources():
    docker = FakeDocker(tls_incomplete=True)
    report = checker.probe(docker)
    assert not report["success"] and report["cleanup"] == "confirmed"
    assert report["error_type"] == "ValueError" and docker.runs == 3


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


@pytest.mark.parametrize(
    "case",
    [
        {"not_internal": True},
        {"foreign_network": True},
        {"unexpected_endpoint": True},
        {"replaced_container": True},
    ],
)
def test_cleanup_prevalidates_network_and_all_container_interfaces_before_removal(case):
    docker = FakeDocker(run_failure=True, **case)
    report = checker.probe(docker)
    assert not report["success"] and report["cleanup"] == "pending_review"
    assert not any(args[:2] in (("container", "rm"), ("network", "rm")) for args in docker.calls)


@pytest.mark.parametrize("change", ["network_identity", "late_endpoint"])
def test_cleanup_rechecks_network_identity_and_new_endpoints_after_own_container_removal(change):
    class ChangingDocker(FakeDocker):
        removed = False

        def command(self, *args, **kwargs):
            result = super().command(*args, **kwargs)
            if args[:2] == ("container", "rm"):
                self.removed = True
            return result

        def inspect(self, kind, name):
            record = super().inspect(kind, name)
            if kind == "network" and self.removed:
                if change == "network_identity":
                    record["Id"] = "replacement-network"
                else:
                    record["Containers"] = {"late-foreign-endpoint": {}}
            return record

    docker = ChangingDocker(run_failure=True)
    report = checker.probe(docker)
    assert not report["success"] and report["cleanup"] == "pending_review"
    assert any(args[:2] == ("container", "rm") for args in docker.calls)
    assert not any(args[:2] == ("network", "rm") for args in docker.calls)


class NdpDocker:
    def __init__(self, *, failure=None):
        self.calls, self.present = [], set()
        self.failure, self.waited = failure, False
        self.evidence = {
            "ndp_denied": "timeout",
            "denied_solicitations": 1,
            "accepted_solicitations": 0,
            "accepted_advertisements": 1,
            "accepted_neighbor_messages": 1,
            "neighbor": "resolved_on_eth0",
            "tls": "verified",
            "pinned_peer": "own_global_unicast_peer",
            "uid": 10001,
        }

    def command(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ("network", "create"):
            self.network, self.token = args[-1], args[-2].split("=", 1)[1]
            self.subnet = str(ipaddress.ip_network(args[args.index("--subnet") + 1]))
        elif args[0] == "run":
            name = args[args.index("--name") + 1]
            if "-d" in args:
                self.peer = name
                self.target = str(ipaddress.ip_address(args[args.index("--ip6") + 1]))
                self.present.add(name)
                return "own_peer_id"
            if self.failure == "timeout":
                self.present.add(name)
                raise subprocess.TimeoutExpired("docker", 40)
            if self.failure == "missing_ndp":
                self.evidence["accepted_neighbor_messages"] = 0
            return json.dumps(self.evidence)
        elif args[0] == "logs":
            ready = json.dumps({"ready": True, "uid": 10001})
            if not self.waited:
                return ready
            return (
                ready
                + "\n"
                + json.dumps(
                    {
                        "http_requests": 1,
                        "sni_verified": self.failure != "peer_tls",
                        "headers_only": True,
                        "uid": 10001,
                    }
                )
            )
        elif args[0] == "wait":
            self.waited = True
            return "1" if self.failure == "peer_exit" else "0"
        elif args[:2] == ("container", "ls"):
            return "\n".join(sorted(self.present))
        elif args[:2] == ("container", "rm"):
            self.present.remove(args[-1])
        return ""

    def inspect(self, kind, name):
        if kind == "container":
            return {
                "Id": name,
                "Config": {
                    "Labels": {
                        "vigil.qa.token": "foreign"
                        if self.failure == "foreign_peer"
                        else self.token
                    }
                },
                "State": {"Running": True},
                "NetworkSettings": {
                    "Networks": {
                        self.network: {
                            "GlobalIPv6Address": "3000::bad"
                            if self.failure == "peer_address"
                            else self.target,
                        }
                    }
                },
            }
        return {
            "Id": self.network,
            "Labels": {"vigil.qa.token": self.token},
            "Internal": True,
            "EnableIPv6": True,
            "IPAM": {"Config": [{"Subnet": self.subnet}]},
            "Containers": {name: {} for name in self.present}
            | ({"unexpected": {}} if self.failure == "unexpected_endpoint" else {}),
        }


@pytest.mark.parametrize(
    "hextets,target",
    [
        ("000100020003", "3000:1:2:3::1"),
        ("000100020000", "3000:1:2::1"),
        ("000000000000", "3000::1"),
    ],
)
def test_ndp_proof_handles_advertisement_and_canonical_ipv6_prefix(monkeypatch, hextets, target):
    monkeypatch.setattr(checker, "uuid4", lambda: SimpleNamespace(hex=hextets + "a" * 20))
    docker = NdpDocker()
    report = checker.ndp_probe(docker)
    assert report["success"] and report["cleanup"] == "confirmed"
    assert report["target"] == target
    assert report["probe"]["accepted_solicitations"] == 0
    assert ("network", "rm", report["network"]) in docker.calls
    runs = [args for args in docker.calls if args[0] == "run"]
    assert len(runs) == 2 and all("--read-only" in args and "--ip6" in args for args in runs)
    assert all("-p" not in args and "--publish" not in args for args in runs)


@pytest.mark.parametrize(
    "failure", ["missing_ndp", "peer_tls", "peer_exit", "peer_address", "timeout"]
)
def test_ndp_proof_failure_cleans_own_endpoints_without_success(failure):
    docker = NdpDocker(failure=failure)
    report = checker.ndp_probe(docker)
    assert not report["success"] and report["cleanup"] == "confirmed"
    assert docker.present == set()
    assert ("network", "rm", report["network"]) in docker.calls


def test_ndp_foreign_peer_prevents_any_cleanup_mutation():
    docker = NdpDocker(failure="foreign_peer")
    report = checker.ndp_probe(docker)
    assert not report["success"] and report["cleanup"] == "pending_review"
    assert not any(args[:2] in (("container", "rm"), ("network", "rm")) for args in docker.calls)


def test_ndp_unexpected_endpoint_is_preserved_for_review():
    docker = NdpDocker(failure="unexpected_endpoint")
    report = checker.ndp_probe(docker)
    assert not report["success"] and report["cleanup"] == "pending_review"
    assert ("network", "rm", report["network"]) not in docker.calls
    assert not any(args[:2] == ("container", "rm") for args in docker.calls)


def test_cli_does_not_report_success_when_ndp_cleanup_is_uncertain(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "Docker", lambda: object())
    monkeypatch.setattr(
        checker,
        "probe",
        lambda *args, **kwargs: {
            "token": "a" * 32,
            "success": True,
            "cleanup": "confirmed",
        },
    )
    monkeypatch.setattr(
        checker,
        "ndp_probe",
        lambda *args, **kwargs: {
            "success": False,
            "cleanup": "pending_review",
        },
    )
    assert checker.main([]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["success"] is False and result["cleanup"] == "pending_review"
