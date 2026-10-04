"""Container routing must preserve credentials/options and prove local service identity."""

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "verify_backend_container.py"
SPEC = importlib.util.spec_from_file_location("verify_backend_container", MODULE)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
URL = "postgresql+asyncpg://owner:p%40ss%3Aword@127.0.0.1:55433/vigil?timeout=3"


def records():
    return {
        "network": {"Labels": {"com.docker.compose.project": "vigil"}},
        "container": {
            "Config": {
                "Labels": {
                    "com.docker.compose.project": "vigil",
                    "com.docker.compose.service": "postgres",
                }
            },
            "State": {"Running": True},
            "NetworkSettings": {
                "Networks": {"vigil_default": {}},
                "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55433"}]},
            },
        },
    }


def route(mapping, url=URL):
    return runner.container_url(
        url,
        network="vigil_default",
        service="postgres",
        port=5432,
        reader=lambda kind, name: mapping[kind],
    )


def test_guarded_internal_route_preserves_encoded_auth_database_and_query():
    assert route(records()) == URL.replace("127.0.0.1:55433", "postgres:5432")


@pytest.mark.parametrize(
    "case",
    [
        "project",
        "service",
        "network",
        "binding_host",
        "binding_port",
        "stopped",
        "network_owner",
        "missing_binding",
    ],
)
def test_internal_route_refuses_mismatched_resource(case):
    mapping = deepcopy(records())
    if case in {"project", "service"}:
        mapping["container"]["Config"]["Labels"]["com.docker.compose." + case] = "foreign"
    elif case == "network":
        mapping["container"]["NetworkSettings"]["Networks"] = {"foreign": {}}
    elif case == "binding_host":
        mapping["container"]["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    elif case == "binding_port":
        mapping["container"]["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = "5432"
    elif case == "stopped":
        mapping["container"]["State"]["Running"] = False
    elif case == "network_owner":
        mapping["network"]["Labels"]["com.docker.compose.project"] = "foreign"
    else:
        mapping["container"]["NetworkSettings"]["Ports"]["5432/tcp"] = None
    with pytest.raises(ValueError):
        route(mapping)


def test_internal_route_rejects_remote_url_before_inspection():
    def unexpected(*args):
        pytest.fail("Remote URL reached local Docker inspection")

    with pytest.raises(ValueError):
        runner.container_url(
            URL.replace("127.0.0.1", "remote.test"),
            network="vigil_default",
            service="postgres",
            port=5432,
            reader=unexpected,
        )


def test_gateway_fallback_and_remote_urls_do_not_inspect_or_change_auth():
    assert runner.container_url(URL, service="postgres", port=5432) == URL.replace(
        "127.0.0.1", "host.docker.internal"
    )
    remote = URL.replace("127.0.0.1", "remote.test")
    assert runner.container_url(remote, service="postgres", port=5432) == remote


def test_setup_failure_does_not_run_container_or_print_private_url(monkeypatch, capsys):
    monkeypatch.setenv("VIGIL_TEST_DATABASE_URL", URL)
    monkeypatch.setattr(
        runner, "arguments", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError(URL))
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("Container started after bad guard"),
    )
    assert runner.main(["--network", "vigil_default"]) == 1
    assert capsys.readouterr().out == "backend_container_setup_failed:ValueError\n"


def test_readonly_source_and_ca_used_only_during_dev_dependency_downloads(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    ca = tmp_path / "public.pem"
    ca.write_text("public test certificate")
    args = runner.arguments("", "", ca_file=ca)
    assert any("target=/verification,readonly" in value for value in args)
    assert any("target=/tmp/public-ca.pem,readonly" in value for value in args)
    assert args[-3:-1] == ["sh", "-ec"]
    assert args[-1].index("unset SSL_CERT_FILE") < args[-1].index("python -m pytest")
    assert "uv sync --frozen" in args[-1]
