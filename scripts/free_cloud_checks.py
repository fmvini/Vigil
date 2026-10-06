"""Run one bounded, protected cloud batch on an exclusively owned Docker bridge.

Credentials use a private temporary env file, never command arguments or logs.
The trusted relay keeps database TLS intact and is the only internal exemption.
"""

import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
POOLER = re.compile(r"ep-[a-z0-9-]+\.(?:[a-z0-9-]+\.)*neon\.tech\Z")
LABEL = "vigil.cloud.run"


def configuration(environment):
    url = environment.get("VIGIL_DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "postgresql+asyncpg"
        or not parsed.hostname
        or not POOLER.fullmatch(parsed.hostname)
        or parsed.hostname.split(".")[0].endswith("-pooler")
        or (parsed.port or 5432) != 5432
        or not parsed.username
        or not parsed.password
        or parsed.path != "/neondb"
        or parsed.query
        or parsed.fragment
        or any(c in url for c in "\r\n\0")
    ):
        raise ValueError("Configure the direct Neon PostgreSQL URL without query options")
    settings = {
        "VIGIL_DATABASE_URL": url,
        "VIGIL_DATABASE_SCHEMA": "vigil",
        "VIGIL_DATABASE_SSL": "true",
        "VIGIL_DATABASE_POOL_SIZE": "2",
        "VIGIL_DATABASE_MAX_OVERFLOW": "0",
        "VIGIL_READINESS_TIMEOUT_SECONDS": "10",
        "VIGIL_ENVIRONMENT": "prod",
        "VIGIL_ALLOWED_ORIGINS": '["https://batch.vigil.invalid"]',
        "VIGIL_REDIS_ENABLED": "false",
        "VIGIL_MINIMUM_INTERVAL_SECONDS": "900",
        "VIGIL_SCHEDULED_CHECKS_INTERVAL_SECONDS": "900",
        "VIGIL_PIPELINE_ENABLED": "true",
        "VIGIL_MONITORING_NETWORK_ENABLED": "true",
    }
    return parsed.hostname, settings


def resolve_upstream(host):
    records = socket.getaddrinfo(host, 5432, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    values = sorted({record[4][0] for record in records})
    if not values or len(values) > 8 or any(not ipaddress.ip_address(v).is_global for v in values):
        raise ValueError("Database upstream must resolve exclusively to public addresses")
    return ",".join(values)


class Docker:
    def command(self, *args, timeout=60):
        result = subprocess.run(
            ["docker", *map(str, args)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("Docker operation failed: " + args[0])
        return result.stdout.strip()

    def inspect(self, kind, identifier):
        values = json.loads(self.command(kind, "inspect", identifier))
        if len(values) != 1:
            raise ValueError("Ambiguous resource ownership")
        return values[0]


def cleanup(docker, network, containers, token):
    record = docker.inspect("network", network)
    if record.get("Id") != network or record.get("Labels", {}).get(LABEL) != token:
        raise ValueError("Foreign network: cleanup refused")
    if set(record.get("Containers", {})) - set(containers):
        raise ValueError("Unexpected endpoint: cleanup refused")
    for identifier in containers:
        candidate = docker.inspect("container", identifier)
        if (
            candidate.get("Id") != identifier
            or candidate.get("Config", {}).get("Labels", {}).get(LABEL) != token
            or set(candidate.get("NetworkSettings", {}).get("Networks", {})) != {record["Name"]}
        ):
            raise ValueError("Foreign container: cleanup refused")
    for identifier in containers:
        docker.command("container", "rm", "--force", identifier)
    record = docker.inspect("network", network)
    if (
        record.get("Id") != network
        or record.get("Labels", {}).get(LABEL) != token
        or record.get("Containers")
    ):
        raise ValueError("Network changed: cleanup refused")
    docker.command("network", "rm", network)


def run(environment, docker=None):
    host, settings = configuration(environment)
    upstream = resolve_upstream(host)
    docker = docker or Docker()
    token = uuid4().hex
    network = None
    containers = []
    report = {"completed": False, "cleanup": "not_needed"}
    with tempfile.TemporaryDirectory(prefix="vigil-cloud-") as directory:
        directory = Path(directory)
        ca = environment.get("VIGIL_DATABASE_CA_PEM", "").strip()
        mounts = []
        if ca:
            ca_file = directory / "database-ca.pem"
            ca_file.write_text(ca + "\n", encoding="utf-8")
            ca_file.chmod(0o644)  # Certificate is public; dropped worker UID must read it.
            settings["VIGIL_DATABASE_SSL_CA_FILE"] = "/run/vigil/database-ca.pem"
            mounts += [
                "--mount",
                f"type=bind,src={ca_file},dst=/run/vigil/database-ca.pem,readonly",
            ]
        private_env = directory / "batch.env"
        private_env.write_text("".join(f"{k}={v}\n" for k, v in settings.items()), encoding="utf-8")
        private_env.chmod(0o600)
        try:
            network = docker.command(
                "network",
                "create",
                "--label",
                LABEL + "=" + token,
                "vigil-cloud-" + token,
            )
            relay = docker.command(
                "create",
                "--name",
                "vigil-relay-" + token,
                "--network",
                "vigil-cloud-" + token,
                "--network-alias",
                host,
                "--label",
                LABEL + "=" + token,
                "--read-only",
                "--user",
                "10001:10001",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--memory",
                "64m",
                "--cpus",
                "0.25",
                "--pids-limit",
                "32",
                "--env",
                "PYTHONDONTWRITEBYTECODE=1",
                "--env",
                "VIGIL_POOLER_HOST=" + host,
                "--env",
                "VIGIL_POOLER_ADDRESSES=" + upstream,
                "--mount",
                f"type=bind,src={ROOT / 'infra/free-cloud/pg_relay.py'},dst=/relay.py,readonly",
                "python:3.13-slim",
                "python",
                "/relay.py",
            )
            containers.append(relay)
            docker.command("start", relay)
            for _ in range(50):
                if "pooler_relay_ready" in docker.command("logs", relay):
                    break
                if not docker.inspect("container", relay).get("State", {}).get("Running"):
                    raise RuntimeError("Pooler relay failed to start")
                time.sleep(0.2)
            else:
                raise TimeoutError("Pooler relay startup deadline")
            batch = docker.command(
                "create",
                "--name",
                "vigil-batch-" + token,
                "--network",
                "vigil-cloud-" + token,
                "--label",
                LABEL + "=" + token,
                "--read-only",
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
                "no-new-privileges:true",
                "--memory",
                "512m",
                "--cpus",
                "1",
                "--pids-limit",
                "64",
                "--tmpfs",
                "/tmp:size=32m,mode=1777",
                "--env-file",
                private_env,
                *mounts,
                "vigil-cloud-batch:local",
            )
            containers.append(batch)
            docker.command("start", batch)
            exit_code = docker.command("wait", batch, timeout=120)
            # Only a valid JSON summary is exposed; native errors/logs stay private.
            lines = docker.command("logs", batch).splitlines()
            summary = json.loads(lines[-1])
            allowed_fields = {
                "status",
                "attempts",
                "jobs_admitted",
                "job_states",
                "backlog",
                "deferred",
                "deadline_reached",
                "retention",
                "error_code",
                "stage",
                "cleanup_error_code",
            }
            if not isinstance(summary, dict) or set(summary) - allowed_fields:
                raise ValueError("Missing batch summary")
            report["batch"] = summary
            report["completed"] = exit_code == "0" and summary.get("status") == "ok"
        except Exception as error:
            report["error_type"] = type(error).__name__
        finally:
            if network:
                try:
                    cleanup(docker, network, containers, token)
                    report["cleanup"] = "confirmed"
                except Exception as error:
                    report["completed"] = False
                    report["cleanup"] = "pending_review"
                    report["cleanup_error_type"] = type(error).__name__
    return report


def main():
    try:
        report = run(os.environ)
    except Exception as error:
        report = {
            "completed": False,
            "error_type": type(error).__name__,
            "cleanup": "not_needed",
        }
    print(json.dumps(report, sort_keys=True))
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    sys.exit(main())
