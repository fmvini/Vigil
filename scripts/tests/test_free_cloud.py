"""Deployment boundaries: secrets, relay resolution and exclusive cleanup."""

import asyncio
import importlib.util
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checks = load("free_checks", "scripts/free_cloud_checks.py")
relay = load("pg_relay", "infra/free-cloud/pg_relay.py")
egress = load("free_egress", "infra/worker/egress.py")
URL = "postgresql://neondb_owner:p%40ss@ep-example-test.us-east-2.aws.neon.tech:5432/neondb"


def test_cloud_credentials_stay_server_side_and_execution_opt_in():
    host, settings = checks.configuration({"VIGIL_DATABASE_URL": URL})
    assert host == "ep-example-test.us-east-2.aws.neon.tech"
    assert settings["VIGIL_DATABASE_URL"].startswith("postgresql+asyncpg://")
    assert settings["VIGIL_DATABASE_SSL"] == "true"
    assert settings["VIGIL_DATABASE_SCHEMA"] == "vigil"
    assert settings["VIGIL_REDIS_ENABLED"] == "false"


@pytest.mark.parametrize(
    "url",
    [
        "",
        URL + "\nVIGIL_EGRESS_READY=1",
        URL.replace(":5432", ":6543"),
        URL.replace("neon.tech", "neon.tech.evil.test"),
        URL + "?sslmode=disable",
        URL.replace("/neondb", "/another"),
        URL.replace("p%40ss", ""),
        URL.replace("postgresql://", "http://"),
        URL.replace("ep-example-test.", "ep-example-test-pooler."),
    ],
)
def test_cloud_rejects_wrong_pooler_or_secret_injection(url):
    with pytest.raises(ValueError):
        checks.configuration({"VIGIL_DATABASE_URL": url})


@pytest.mark.parametrize("values", [[], ["127.0.0.1"], ["10.0.0.1"], ["8.8.8.8", "::1"]])
def test_relay_rejects_entire_private_or_mixed_answer(values):
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, 5432)) for value in values]

    with pytest.raises(ValueError):
        asyncio.run(relay.addresses("ep-example-test.us-east-2.aws.neon.tech", resolver=resolve))


def test_relay_resolves_once_and_pins_all_public_addresses():
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 5432))]

    assert asyncio.run(
        relay.addresses("ep-example-test.us-east-2.aws.neon.tech", resolver=resolve)
    ) == ["8.8.8.8"]


def test_database_only_keeps_internal_5432_and_does_not_resolve_redis():
    calls = []

    def resolve(host, port, **kwargs):
        calls.append((host, port))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.20.0.2", port))]

    env = {"VIGIL_DATABASE_URL": URL, "VIGIL_WORKER_CONTROL_MODE": "database-only"}
    assert egress.control_endpoints(env, resolver=resolve) == [("172.20.0.2", 5432)]
    assert len(calls) == 1
    with pytest.raises(ValueError):
        egress.control_endpoints({**env, "VIGIL_WORKER_CONTROL_MODE": "anything"}, resolver=resolve)


@pytest.mark.parametrize("foreign", ["network", "container", "endpoint", "late_endpoint"])
def test_cleanup_never_removes_foreign_resources(foreign):
    class Docker:
        removed = False
        calls = []

        def inspect(self, kind, identifier):
            if kind == "network":
                return {
                    "Id": "network",
                    "Name": "own",
                    "Labels": {checks.LABEL: "foreign" if foreign == "network" else "token"},
                    "Containers": {"unknown": {}}
                    if foreign == "endpoint" or (foreign == "late_endpoint" and self.removed)
                    else {},
                }
            return {
                "Id": "container",
                "Config": {
                    "Labels": {checks.LABEL: "foreign" if foreign == "container" else "token"}
                },
                "NetworkSettings": {"Networks": {"own": {}}},
            }

        def command(self, *args):
            self.calls.append(args)
            self.removed = True

    docker = Docker()
    with pytest.raises(ValueError):
        checks.cleanup(docker, "network", ["container"], "token")
    assert not any(call[:2] == ("network", "rm") for call in docker.calls)
    if foreign != "late_endpoint":
        assert not docker.calls


def test_orchestrator_resolves_before_alias_and_rejects_private_dns(monkeypatch):
    def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 5432))]

    monkeypatch.setattr(checks.socket, "getaddrinfo", resolve)
    with pytest.raises(ValueError):
        checks.resolve_upstream("ep-example-test.us-east-2.aws.neon.tech")


def test_pinned_relay_addresses_reject_internal_alias_resolution():
    assert relay.validate_addresses(["8.8.8.8"]) == ["8.8.8.8"]
    with pytest.raises(ValueError):
        relay.validate_addresses(["172.20.0.2"])
