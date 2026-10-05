"""Load runner refuses incomplete proofs and foreign Docker resources."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "pipeline_load_check", ROOT / "scripts/pipeline_load_check.py"
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def observation(jobs=2):
    return {
        "pipeline": {
            "protocol_version": 1,
            "run_id": None,
            "success": True,
            "counts": {
                key: jobs
                for key in (
                    "programmed",
                    "scheduled",
                    "published",
                    "claimed",
                    "committed",
                    "acknowledged",
                    "xack_confirmed",
                    "results",
                )
            }
            | {"errors": 0},
            "cleanup": {"schema": "confirmed", "redis": "confirmed"},
            "backlog": {"final_lag": 0, "final_pel": 0, "final_pg_open": 0},
            "invariants": {
                "stage_order_verified": True,
                "commit_visibility_separate_connection": True,
                "measurement_samples_complete": True,
            },
            "concurrency": {
                "callback_limit": 50,
                "max_callbacks": 2,
                "max_http": 2,
                "host_limit": 5,
                "global_executor_limit": 50,
            },
            "latencies_ms": {
                phase: {"sample_count": jobs, "p50": 1, "p95": 2, "p99": 3}
                for phase in checker.LATENCY_PHASES
            },
        },
        "tls": {
            "http_requests": jobs,
            "closed_after_headers": jobs,
            "sni_verified": True,
            "host_verified": True,
            "headers_only": True,
            "uid": 10001,
            "capabilities": 0,
        },
    }


class FakeDocker:
    def __init__(self, unsafe=None):
        self.calls, self.containers = [], {}
        self.unsafe = unsafe
        self.observation = observation()

    def command(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ("image", "inspect"):
            return json.dumps([{"Id": "sha256:own-image"}])
        if args[:2] == ("network", "create"):
            self.network = args[-1]
            self.token = self.network.removeprefix("vigil-load-qa-")
            self.observation["pipeline"]["run_id"] = self.token
            self.record = {
                "Id": "own-network-id",
                "Internal": self.unsafe != "noninternal",
                "Labels": {"vigil.qa.token": self.token},
                "Containers": {},
            }
        elif args[0] == "run":
            name = args[args.index("--name") + 1]
            if "redis" in name and self.unsafe == "redis_start":
                raise RuntimeError("Own service failed to start")
            identifier = name + "-id"
            networks = {self.network: {"IPAddress": "172.29.0.2" if "pg" in name else "172.29.0.3"}}
            if self.unsafe == "foreign_interface":
                networks["shared-network"] = {}
            self.containers[name] = {
                "Id": identifier,
                "Config": {"Labels": {"vigil.qa.token": self.token}},
                "NetworkSettings": {"Networks": networks},
                "State": {"Running": False, "ExitCode": 0},
            }
            self.record["Containers"][identifier] = {}
            if self.unsafe == "foreign_endpoint":
                self.record["Containers"]["foreign-id"] = {}
            return identifier
        elif args[:2] == ("container", "ls"):
            return "\n".join(self.containers)
        elif args[:2] == ("container", "rm"):
            identifier = args[-1]
            name = next(
                name for name, record in self.containers.items() if record["Id"] == identifier
            )
            del self.containers[name]
            self.record["Containers"].pop(identifier)
        elif args[0] == "logs":
            return json.dumps(self.observation)
        return ""

    def inspect(self, kind, name):
        return self.record if kind == "network" else self.containers[name]


@pytest.mark.parametrize("unsafe", ["noninternal", "foreign_interface", "foreign_endpoint"])
def test_foreign_load_resources_are_preserved_before_any_removal(unsafe):
    docker = FakeDocker(unsafe)
    result = checker.probe(docker, jobs=2, duration_seconds=0)
    assert result["success"] is False and result["cleanup"] == "pending_review"
    assert not any(call[:2] in {("container", "rm"), ("network", "rm")} for call in docker.calls)


def test_partial_service_start_cleans_only_own_resources():
    docker = FakeDocker("redis_start")
    result = checker.probe(docker, jobs=2, duration_seconds=0)
    assert result["success"] is False and result["cleanup"] == "confirmed"
    assert result["failure"]["stage"] == "redis"
    removals = [call[-1] for call in docker.calls if call[:2] == ("container", "rm")]
    assert (
        len(removals) == 1
        and removals[0].startswith("vigil-load-pg-")
        and removals[0].endswith("-id")
    )
    assert ("network", "rm", "own-network-id") in docker.calls


@pytest.mark.parametrize("address", ["127.0.0.1", "93.184.216.34", "fd00::1"])
def test_control_endpoints_are_only_inspected_private_ipv4(address):
    docker = FakeDocker()
    original = docker.inspect

    def inspect(kind, name):
        record = original(kind, name)
        if kind == "container":
            record["NetworkSettings"]["Networks"][docker.network]["IPAddress"] = address
        return record

    docker.inspect = inspect
    result = checker.probe(docker, jobs=2, duration_seconds=0)
    assert result["success"] is False and result["cleanup"] == "confirmed"
    assert result["failure"]["stage"] == "worker"
    assert len([call for call in docker.calls if call[0] == "run"]) == 2


@pytest.mark.parametrize(
    "missing", ["count", "fixture_cleanup", "pending_ack", "tls_close", "caps"]
)
def test_exit_zero_does_not_accept_incomplete_load_proof(missing):
    docker = FakeDocker()
    if missing == "count":
        docker.observation["pipeline"]["counts"]["committed"] = 1
    elif missing == "fixture_cleanup":
        docker.observation["pipeline"]["cleanup"]["schema"] = "failed"
    elif missing == "pending_ack":
        docker.observation["pipeline"]["backlog"]["final_pel"] = 1
    elif missing == "tls_close":
        docker.observation["tls"]["closed_after_headers"] = 1
    else:
        docker.observation["tls"]["capabilities"] = 1
    result = checker.probe(docker, jobs=2, duration_seconds=0)
    assert result["success"] is False and result["failure"]["stage"] == "proof"
    assert result["cleanup"] == "confirmed"


@pytest.mark.parametrize(
    "section,key", [("tls", "http_requests"), ("tls", "capabilities"), ("backlog", "final_pel")]
)
def test_boolean_json_fields_cannot_prove_tls_or_a_drained_queue(section, key):
    value = observation(jobs=1)
    value["pipeline"]["run_id"] = "own-run"
    value["pipeline"]["concurrency"].update(max_callbacks=1, max_http=1)
    target = value["tls"] if section == "tls" else value["pipeline"]["backlog"]
    target[key] = key == "http_requests"
    with pytest.raises(ValueError):
        checker.validate_observation(value, 1, run_id="own-run", callback_limit=50)


@pytest.mark.parametrize(
    "section,key,invalid,callback_limit",
    [
        ("pipeline", "protocol_version", True, 50),
        ("pipeline", "protocol_version", 1.0, 50),
        ("concurrency", "callback_limit", True, 1),
        ("concurrency", "callback_limit", 50.0, 50),
        ("concurrency", "host_limit", 5.0, 50),
        ("concurrency", "global_executor_limit", 50.0, 50),
        ("tls", "uid", 10001.0, 50),
    ],
)
def test_protocol_privileges_and_limits_require_json_integers(
    section, key, invalid, callback_limit
):
    value = observation(jobs=1)
    value["pipeline"]["run_id"] = "own-run"
    value["pipeline"]["concurrency"].update(
        callback_limit=callback_limit, max_callbacks=1, max_http=1
    )
    target = value[section] if section != "concurrency" else value["pipeline"][section]
    target[key] = invalid
    with pytest.raises(ValueError):
        checker.validate_observation(value, 1, run_id="own-run", callback_limit=callback_limit)


@pytest.mark.parametrize(
    "invalid",
    [
        "version",
        "identity",
        "visibility",
        "order",
        "xack",
        "concurrency",
        "samples",
        "negative",
        "nonfinite",
        "quantile_order",
    ],
)
def test_success_flag_cannot_replace_stage_measurements_and_invariants(invalid):
    docker = FakeDocker()
    pipeline = docker.observation["pipeline"]
    if invalid == "version":
        pipeline["protocol_version"] = 2
    elif invalid == "identity":
        # Alter identity after resource creation has assigned the own token.
        original = docker.command

        def command(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[0] == "logs":
                pipeline["run_id"] = "foreign-run"
                return json.dumps(docker.observation)
            return result

        docker.command = command
    elif invalid in ("visibility", "order"):
        key = (
            "commit_visibility_separate_connection"
            if invalid == "visibility"
            else "stage_order_verified"
        )
        pipeline["invariants"][key] = False
    elif invalid == "xack":
        pipeline["counts"]["xack_confirmed"] = 1
    elif invalid == "concurrency":
        pipeline["concurrency"]["max_http"] = 6
    else:
        measurement = pipeline["latencies_ms"]["result_commit_to_xack"]
        key, value = {
            "samples": ("sample_count", 1),
            "negative": ("p50", -1),
            "nonfinite": ("p99", float("inf")),
            "quantile_order": ("p50", 4),
        }[invalid]
        measurement[key] = value
    result = checker.probe(docker, jobs=2, duration_seconds=0)
    assert result["success"] is False and result["failure"]["stage"] == "proof"
    assert result["cleanup"] == "confirmed"


def test_real_proof_contract_and_disposable_topology_are_required():
    docker = FakeDocker()
    result = checker.probe(docker, jobs=2, duration_seconds=0)
    assert result["success"] is True and result["cleanup"] == "confirmed"
    starts = [call for call in docker.calls if call[0] == "run"]
    assert len(starts) == 3
    assert all(
        "--read-only" in call and "--publish" not in call and "-p" not in call for call in starts
    )
    assert all("--volume" not in call and "-v" not in call for call in starts)
    worker = starts[-1]
    assert (
        "VIGIL_PIPELINE_ENABLED=false" in worker
        and "VIGIL_MONITORING_NETWORK_ENABLED=false" in worker
    )
    assert "VIGIL_TEST_PIPELINE_LOAD_QA=1" in worker and "--cap-drop" in worker


@pytest.mark.parametrize("code", ["claim_not_committed", "postgresql://private:secret@host/db"])
def test_failed_helper_only_exposes_a_fixed_safe_error_code(code):
    class FailedHelper(FakeDocker):
        def command(self, *args, **kwargs):
            result = super().command(*args, **kwargs)
            if args[0] == "run" and "worker" in args[args.index("--name") + 1]:
                self.containers[args[args.index("--name") + 1]]["State"]["ExitCode"] = 1
                self.observation = {"failure_code": code}
            return result

    docker = FailedHelper()
    result = checker.probe(docker, jobs=2, duration_seconds=0)
    assert result["success"] is False and result["cleanup"] == "confirmed"
    assert result.get("helper_failure_code") == (code if code == "claim_not_committed" else None)
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize(
    "jobs,duration,limit,drain",
    [
        (0, 0, 50, 30),
        (2001, 0, 50, 30),
        (1, float("nan"), 50, 30),
        (1, 601, 50, 30),
        (1, 0, 51, 30),
        (1, 0, True, 30),
        (1, 0, 50, 0),
    ],
)
def test_invalid_campaign_never_contacts_docker(jobs, duration, limit, drain):
    docker = FakeDocker()
    with pytest.raises(ValueError):
        checker.probe(
            docker,
            jobs=jobs,
            duration_seconds=duration,
            callback_limit=limit,
            drain_timeout_seconds=drain,
        )
    assert not docker.calls


@pytest.mark.parametrize(
    "value,expected",
    [("512MiB", 512 * 1024**2), ("1.5GiB", int(1.5 * 1024**3)), ("1.5MB", 1500000), ("0B", 0)],
)
def test_resource_units_keep_binary_and_decimal_scales_distinct(value, expected):
    assert checker.memory_bytes(value) == expected


@pytest.mark.parametrize(
    "section,key",
    [("counts", "xack_confirmed"), ("counts", "errors"), ("latencies_ms", "sample_count")],
)
def test_boolean_json_fields_are_not_numeric_evidence(section, key):
    value = observation(jobs=1)
    value["pipeline"]["run_id"] = "own-run"
    value["pipeline"]["concurrency"].update(max_callbacks=1, max_http=1)
    target = value["pipeline"][section]
    if section == "latencies_ms":
        target = target["xack_round_trip"]
    target[key] = key != "errors"
    with pytest.raises(ValueError):
        checker.validate_observation(value, 1, run_id="own-run", callback_limit=50)
