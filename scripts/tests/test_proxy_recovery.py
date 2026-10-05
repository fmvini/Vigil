import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "proxy_recovery_check", ROOT / "scripts" / "proxy_recovery_check.py"
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class FakeDocker:
    def __init__(self):
        self.commands = []
        self.network = {
            "Internal": True,
            "Labels": {"vigil.qa.token": "own"},
            "Containers": {"id": {}},
        }
        self.container = {
            "Id": "id",
            "Config": {"Labels": {"vigil.qa.token": "own"}},
            "NetworkSettings": {"Networks": {"qa-network": {"IPAddress": "172.19.0.2"}}},
        }

    def inspect(self, kind, name):
        return self.network if kind == "network" else self.container

    def command(self, *args):
        self.commands.append(args)
        if args[:2] == ("container", "ls"):
            return "qa-container"
        if args[:3] == ("container", "rm", "--force"):
            self.network["Containers"] = {}
        return ""


@pytest.mark.parametrize(
    "unsafe",
    ["network_owner", "not_internal", "container_owner", "foreign_network", "foreign_endpoint"],
)
def test_cleanup_refuses_foreign_resources_before_any_mutation(unsafe):
    docker = FakeDocker()
    if unsafe == "network_owner":
        docker.network["Labels"]["vigil.qa.token"] = "foreign"
    elif unsafe == "not_internal":
        docker.network["Internal"] = False
    elif unsafe == "container_owner":
        docker.container["Config"]["Labels"]["vigil.qa.token"] = "foreign"
    elif unsafe == "foreign_network":
        docker.container["NetworkSettings"]["Networks"]["shared"] = {}
    else:
        docker.network["Containers"]["foreign-id"] = {}
    with pytest.raises(ValueError):
        checker.cleanup(docker, "qa-network", ("qa-container",), "own")
    assert not any(
        command[:2] in {("network", "rm"), ("container", "rm")} for command in docker.commands
    )


def test_detached_own_container_can_be_cleaned_after_interrupted_alias_switch():
    docker = FakeDocker()
    docker.container["NetworkSettings"]["Networks"] = {}
    docker.network["Containers"] = {}
    checker.cleanup(docker, "qa-network", ("qa-container",), "own")
    assert ("container", "rm", "--force", "qa-container") in docker.commands
    assert ("network", "rm", "qa-network") in docker.commands


def test_alias_switch_requires_two_exclusive_distinct_addresses_before_disconnect():
    docker = FakeDocker()
    with pytest.raises(ValueError, match="distinct"):
        checker.switch_alias(docker, "qa-network", "qa-container", "other", "own")
    assert not docker.commands


def test_alias_switch_refuses_detached_container_before_disconnect():
    docker = FakeDocker()
    docker.container["NetworkSettings"]["Networks"] = {}
    with pytest.raises(ValueError):
        checker.switch_alias(docker, "qa-network", "qa-container", "other", "own")
    assert not docker.commands
