"""Taskiq/PG17/Redis/TLS campaign against exclusively owned disposable services."""

import argparse
import importlib.util
import ipaddress
import json
import math
import re
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("load_egress_guard", ROOT / "scripts/egress_check.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
Docker = guard.Docker


def options(jobs, duration_seconds, callback_limit, drain_timeout_seconds):
    if not isinstance(jobs, int) or isinstance(jobs, bool) or not 1 <= jobs <= 2000:
        raise ValueError("Invalid bounded QA job count")
    if not math.isfinite(duration_seconds) or not 0 <= duration_seconds <= 600:
        raise ValueError("Invalid bounded QA duration")
    if type(callback_limit) is not int or not 1 <= callback_limit <= 50:
        raise ValueError("Invalid bounded QA callback limit")
    if not math.isfinite(drain_timeout_seconds) or not 1 <= drain_timeout_seconds <= 120:
        raise ValueError("Invalid bounded QA drain deadline")


def exclusive(docker, network, names, token):
    record = docker.inspect("network", network)
    if not record.get("Internal") or record.get("Labels", {}).get("vigil.qa.token") != token:
        raise ValueError("Refusing foreign/noninternal load QA network")
    identifiers = set()
    for name in names:
        container = docker.inspect("container", name)
        if container.get("Config", {}).get("Labels", {}).get("vigil.qa.token") != token or set(
            container.get("NetworkSettings", {}).get("Networks", {})
        ) != {network}:
            raise ValueError("Refusing foreign/multinetwork load QA container")
        identifiers.add(container["Id"])
    if set(record.get("Containers", {})) - identifiers:
        raise ValueError("Refusing load QA network with unexpected endpoints")


def ready(docker, name, arguments, *, timeout=35):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            docker.command("exec", name, *arguments, timeout=3)
            return
        except RuntimeError:
            time.sleep(0.25)
    raise TimeoutError("Own QA service readiness deadline exceeded")


def control_address(docker, name, network):
    value = docker.inspect("container", name)["NetworkSettings"]["Networks"][network]["IPAddress"]
    address = ipaddress.IPv4Address(value)
    if not any(
        address in ipaddress.IPv4Network(cidr)
        for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    ):
        raise ValueError("Own control endpoint needs an internal IPv4 address")
    return address.compressed


def memory_bytes(value):
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(B|kB|KB|KiB|MB|MiB|GB|GiB)", value)
    if not match:
        raise ValueError("Unrecognized Docker memory statistic")
    scales = {
        "B": 1,
        "kB": 1000,
        "KB": 1000,
        "KiB": 1024,
        "MB": 10**6,
        "MiB": 1024**2,
        "GB": 10**9,
        "GiB": 1024**3,
    }
    return int(float(match[1]) * scales[match[2]])


def collect_stats(docker, names, resources):
    output = docker.command("stats", "--no-stream", "--format", "{{json .}}", *names, timeout=8)
    records = [json.loads(line) for line in output.splitlines() if line]
    by_name = {record["Name"]: record for record in records}
    for role, name in zip(("postgres", "redis", "worker_and_tls"), names, strict=True):
        record = by_name.get(name)
        if record is None:
            continue
        cpu = float(record["CPUPerc"].removesuffix("%"))
        memory = memory_bytes(record["MemUsage"].split("/", 1)[0].strip())
        if memory == 0:
            continue  # A process may have exited while Docker collected its statistics.
        if not math.isfinite(cpu) or cpu < 0:
            raise ValueError("Invalid Docker CPU statistic")
        item = resources.setdefault(
            role, {"samples": 0, "max_cpu_percent": 0, "max_memory_bytes": 0}
        )
        item["samples"] += 1
        item["max_cpu_percent"] = max(item["max_cpu_percent"], cpu)
        item["max_memory_bytes"] = max(item["max_memory_bytes"], memory)


LATENCY_PHASES = (
    "schedule_transaction",
    "publication",
    "schedule_to_delivery",
    "delivery_to_claim_commit",
    "claim_to_executor_return",
    "result_commit_to_xack",
    "xack_round_trip",
    "ack_observation",
    "schedule_commit_to_xack",
    "queue_delay",
    "http",
    "commit",
    "finalize_after_executor",
)


def validate_observation(observation, jobs, *, run_id, callback_limit):
    pipeline, tls = observation["pipeline"], observation["tls"]
    if (
        pipeline.get("success") is not True
        or type(pipeline.get("protocol_version")) is not int
        or pipeline.get("protocol_version") != 1
        or pipeline.get("run_id") != run_id
    ):
        raise ValueError("Controlled pipeline did not report success")
    # Counts and ownership cleanup are required even when the subprocess exits zero.
    counts = pipeline["counts"]
    if any(
        type(counts.get(key)) is not int or counts[key] != jobs
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
    ):
        raise ValueError("Incomplete schedule/publication/claim/commit/ACK proof")
    if type(counts.get("errors")) is not int or counts["errors"] != 0:
        raise ValueError("Controlled pipeline reported errors")
    if any(pipeline["cleanup"].get(key) != "confirmed" for key in ("schema", "redis")):
        raise ValueError("Own fixture cleanup was not confirmed")
    if any(
        type(pipeline["backlog"].get(key)) is not int or pipeline["backlog"][key] != 0
        for key in ("final_lag", "final_pel", "final_pg_open")
    ):
        raise ValueError("Controlled pipeline retained outstanding deliveries")
    if any(
        pipeline["invariants"].get(key) is not True
        for key in (
            "stage_order_verified",
            "commit_visibility_separate_connection",
            "measurement_samples_complete",
        )
    ):
        raise ValueError("Missing commit visibility or stage ordering proof")
    concurrency = pipeline["concurrency"]
    if (
        any(
            type(concurrency.get(key)) is not int
            for key in ("callback_limit", "host_limit", "global_executor_limit")
        )
        or concurrency.get("callback_limit") != callback_limit
        or concurrency.get("host_limit") != 5
        or concurrency.get("global_executor_limit") != 50
        or type(concurrency.get("max_callbacks")) is not int
        or not 1 <= concurrency["max_callbacks"] <= min(callback_limit, jobs)
        or type(concurrency.get("max_http")) is not int
        or not 1 <= concurrency["max_http"] <= min(5, callback_limit, jobs)
    ):
        raise ValueError("Incomplete bounded concurrency proof")
    for phase in LATENCY_PHASES:
        measurement = pipeline["latencies_ms"][phase]
        values = [measurement.get(key) for key in ("p50", "p95", "p99")]
        if (
            type(measurement.get("sample_count")) is not int
            or measurement["sample_count"] != jobs
            or any(
                type(value) not in (int, float) or not math.isfinite(value) or value < 0
                for value in values
            )
            or values != sorted(values)
        ):
            raise ValueError("Missing or invalid phase latency measurements")
    if (
        type(tls.get("http_requests")) is not int
        or tls["http_requests"] != jobs
        or type(tls.get("closed_after_headers")) is not int
        or tls["closed_after_headers"] != jobs
        or tls.get("sni_verified") is not True
        or tls.get("host_verified") is not True
        or tls.get("headers_only") is not True
        or type(tls.get("uid")) is not int
        or tls.get("uid") != 10001
        or type(tls.get("capabilities")) is not int
        or tls["capabilities"] != 0
    ):
        raise ValueError("Incomplete physical TLS/privilege proof")


def probe(
    docker,
    *,
    image="vigil-worker-egress:qa",
    jobs=100,
    duration_seconds=60,
    callback_limit=50,
    drain_timeout_seconds=30,
):
    options(jobs, duration_seconds, callback_limit, drain_timeout_seconds)
    token = uuid4().hex
    network = "vigil-load-qa-" + token
    postgres, redis, worker = [
        "vigil-load-" + role + "-" + token for role in ("pg", "redis", "worker")
    ]
    names = (postgres, redis, worker)
    created = False
    report = {
        "token": token,
        "success": False,
        "cleanup": "not_created",
        "campaign": {
            "jobs": jobs,
            "duration_seconds": duration_seconds,
            "callback_limit": callback_limit,
            "drain_timeout_seconds": drain_timeout_seconds,
            "external_checks_executed": False,
        },
        "limits": {
            "worker_cpus": 2,
            "worker_memory_bytes": 512 * 1024**2,
            "postgres_cpus": 2,
            "postgres_memory_bytes": 512 * 1024**2,
            "redis_cpus": 1,
            "redis_memory_bytes": 128 * 1024**2,
            "docker_stats": "sampled working set; combined worker/TLS namespace including setup; CPU percent per logical CPU",
        },
        "resources": {},
    }
    stage = "images"
    try:
        report["images"] = {}
        for role, tag in (
            ("worker", image),
            ("postgres", "postgres:17.11-alpine"),
            ("redis", "redis:7.4.11-alpine"),
        ):
            record = json.loads(docker.command("image", "inspect", tag))[0]
            report["images"][role] = {"tag": tag, "id": record["Id"]}
        stage = "network"
        docker.command(
            "network",
            "create",
            "--internal",
            "--ipv6",
            "--label",
            "vigil.qa.token=" + token,
            network,
        )
        created = True
        exclusive(docker, network, (), token)
        common = ["--label", "vigil.qa.token=" + token, "--network", network, "--read-only"]
        stage = "postgres"
        docker.command(
            "run",
            "-d",
            "--name",
            postgres,
            *common,
            "--network-alias",
            "qa-postgres",
            "--cpus",
            "2",
            "--memory",
            "512m",
            "--tmpfs",
            "/var/lib/postgresql/data:size=256m,mode=0700",
            "--tmpfs",
            "/var/run/postgresql:size=16m,mode=0775",
            "--tmpfs",
            "/tmp:size=16m,mode=1777",
            "-e",
            "POSTGRES_USER=qa",
            "-e",
            "POSTGRES_PASSWORD=qa_fixture_only",
            "-e",
            "POSTGRES_DB=qa",
            "postgres:17.11-alpine",
        )
        exclusive(docker, network, (postgres,), token)
        ready(docker, postgres, ["pg_isready", "-h", "127.0.0.1", "-U", "qa", "-d", "qa"])
        stage = "redis"
        docker.command(
            "run",
            "-d",
            "--name",
            redis,
            *common,
            "--network-alias",
            "qa-redis",
            "--cpus",
            "1",
            "--memory",
            "128m",
            "--tmpfs",
            "/data:size=32m,mode=1777",
            "redis:7.4.11-alpine",
            "redis-server",
            "--bind",
            "0.0.0.0",
            "--protected-mode",
            "no",
            "--save",
            "",
            "--appendonly",
            "no",
            "--maxmemory-policy",
            "noeviction",
        )
        exclusive(docker, network, (postgres, redis), token)
        ready(docker, redis, ["redis-cli", "ping"])
        stage = "worker"
        # Pin the verified private IPv4 controls; dual-stack Docker DNS may also return AAAA.
        database_url = f"postgresql+asyncpg://qa:qa_fixture_only@{control_address(docker, postgres, network)}:5432/qa"
        redis_url = f"redis://{control_address(docker, redis, network)}:6379/0"
        docker.command(
            "run",
            "-d",
            "--name",
            worker,
            *common,
            "--cpus",
            "2",
            "--memory",
            "512m",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "NET_ADMIN",
            "--cap-add",
            "SETUID",
            "--cap-add",
            "SETGID",
            "--cap-add",
            "SETPCAP",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:size=32m,mode=1777",
            "--tmpfs",
            "/home/qa:size=16m,uid=10001,gid=10001,mode=0700",
            "-e",
            "HOME=/home/qa",
            "--mount",
            f"type=bind,source={ROOT / 'backend/app'},target=/app/app,readonly",
            "--mount",
            f"type=bind,source={ROOT / 'backend/tests'},target=/app/tests,readonly",
            "--mount",
            f"type=bind,source={ROOT / 'infra/worker'},target=/qa,readonly",
            "--mount",
            f"type=bind,source={ROOT / 'backend/tests/fixtures/tls'},target=/fixtures,readonly",
            "-e",
            "VIGIL_EGRESS_QA_TOKEN=" + token,
            "-e",
            "VIGIL_TEST_PIPELINE_LOAD_QA=1",
            "-e",
            "VIGIL_PIPELINE_ENABLED=false",
            "-e",
            "VIGIL_MONITORING_NETWORK_ENABLED=false",
            "-e",
            "VIGIL_DATABASE_URL=" + database_url,
            "-e",
            "VIGIL_TEST_DATABASE_URL=" + database_url,
            "-e",
            "VIGIL_REDIS_URL=" + redis_url,
            "-e",
            "VIGIL_TEST_REDIS_URL=" + redis_url,
            "--entrypoint",
            "python",
            image,
            "/qa/qa_pipeline_load.py",
            "--run-id",
            token,
            "--jobs",
            str(jobs),
            "--duration-seconds",
            str(duration_seconds),
            "--callback-limit",
            str(callback_limit),
            "--drain-timeout-seconds",
            str(drain_timeout_seconds),
        )
        exclusive(docker, network, names, token)
        stage = "campaign"
        deadline = time.monotonic() + duration_seconds + drain_timeout_seconds + 55
        while True:
            state = docker.inspect("container", worker)["State"]
            if not state.get("Running"):
                if state.get("ExitCode") != 0:
                    try:
                        diagnostic = json.loads(docker.command("logs", worker))
                        helper = diagnostic.get("pipeline", {})
                        code = diagnostic.get("failure_code", helper.get("failure_code"))
                        if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,64}", code):
                            report["helper_failure_code"] = code
                        if isinstance(helper, dict):
                            report["helper_observation"] = {
                                key: helper[key]
                                for key in (
                                    "counts",
                                    "cleanup",
                                    "sources",
                                    "concurrency",
                                    "backlog",
                                    "latencies_ms",
                                    "database",
                                    "failure_stage",
                                    "exception_type",
                                    "exception_types",
                                )
                                if key in helper
                            }
                    except (ValueError, RuntimeError, AttributeError):
                        pass  # Native/library stderr never becomes a report field.
                    raise RuntimeError("Own load worker exited unsuccessfully")
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Controlled campaign deadline exceeded")
            collect_stats(docker, names, report["resources"])
            time.sleep(0.5)
        stage = "proof"
        observation = json.loads(docker.command("logs", worker))
        validate_observation(observation, jobs, run_id=token, callback_limit=callback_limit)
        report["observation"] = observation
        report["success"] = True
    except Exception as error:
        report["failure"] = {"stage": stage, "type": type(error).__name__}
    finally:
        if created:
            try:
                guard.cleanup(
                    docker, network, worker, token, additional_containers=(postgres, redis)
                )
                report["cleanup"] = "confirmed"
            except Exception as error:
                report["cleanup"] = "pending_review"
                report["cleanup_failure_type"] = type(error).__name__
                report["success"] = False
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="vigil-worker-egress:qa")
    parser.add_argument("--jobs", type=int, default=100)
    parser.add_argument("--duration-seconds", type=float, default=60)
    parser.add_argument("--callback-limit", type=int, default=50)
    parser.add_argument("--drain-timeout-seconds", type=float, default=30)
    args = parser.parse_args(argv)
    options(args.jobs, args.duration_seconds, args.callback_limit, args.drain_timeout_seconds)
    report = probe(
        Docker(),
        image=args.image,
        jobs=args.jobs,
        duration_seconds=args.duration_seconds,
        callback_limit=args.callback_limit,
        drain_timeout_seconds=args.drain_timeout_seconds,
    )
    path = ROOT / ".cache/pipeline-load" / report["token"] / "report.json"
    path.parent.mkdir(parents=True, exist_ok=False)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"success": report["success"], "cleanup": report["cleanup"], "report": str(path)}
        )
    )
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
