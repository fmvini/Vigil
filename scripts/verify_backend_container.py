"""Disposable backend verification, with guarded direct Compose service routing."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]


def inspect(kind, name):
    result = subprocess.run(
        ["docker", kind, "inspect", name], capture_output=True, text=True, timeout=15
    )
    if result.returncode:
        raise ValueError("Expected Compose resource unavailable")
    records = json.loads(result.stdout)
    if len(records) != 1:
        raise ValueError("Expected one Compose resource")
    return records[0]


def container_url(url, *, network=None, service, port, reader=inspect):
    target = urlsplit(url)
    if not target.scheme or not target.hostname:
        raise ValueError("Explicit test URL required")
    if network:
        if target.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Internal routing requires explicit loopback source URL")
        network_record = reader("network", network)
        if network_record.get("Labels", {}).get("com.docker.compose.project") != "vigil":
            raise ValueError("Network must belong to Compose vigil")
        record = reader("container", "vigil-" + service + "-1")
        labels = record.get("Config", {}).get("Labels", {})
        settings = record.get("NetworkSettings", {})
        if (
            labels.get("com.docker.compose.project") != "vigil"
            or labels.get("com.docker.compose.service") != service
            or network not in settings.get("Networks", {})
            or not record.get("State", {}).get("Running")
        ):
            raise ValueError("Service does not match expected project/network/runtime")
        bindings = settings.get("Ports", {}).get(str(port) + "/tcp") or []
        if not any(
            row["HostIp"] == "127.0.0.1" and int(row["HostPort"]) == target.port for row in bindings
        ):
            raise ValueError("Source port does not match the existing loopback service")
        hostname, destination_port = service, port
    else:
        if target.hostname not in {"127.0.0.1", "localhost"}:
            return url
        hostname, destination_port = "host.docker.internal", target.port
    userinfo = target.netloc.rsplit("@", 1)[0] + "@" if "@" in target.netloc else ""
    authority = userinfo + hostname + (":" + str(destination_port) if destination_port else "")
    return urlunsplit(target._replace(netloc=authority))


TEST_COMMAND = """\
if [ -f /tmp/public-ca.pem ]; then
    cat /etc/ssl/certs/ca-certificates.crt /tmp/public-ca.pem > /tmp/test-ca.pem
    export SSL_CERT_FILE=/tmp/test-ca.pem
fi
uv sync --frozen --no-install-project
unset SSL_CERT_FILE
/app/.venv/bin/python -m pytest -q -ra -p no:cacheprovider --junitxml=/reports/backend.xml
"""


def arguments(database_url, redis_url, *, network=None, ca_file=None, image="vigil-api"):
    database = (
        container_url(database_url, network=network, service="postgres", port=5432)
        if database_url
        else ""
    )
    redis = (
        container_url(redis_url, network=network, service="redis", port=6379) if redis_url else ""
    )
    reports = ROOT / ".cache" / "verification"
    reports.mkdir(parents=True, exist_ok=True)
    result = [
        "docker",
        "run",
        "--rm",
        "--mount",
        f"type=bind,source={ROOT / 'backend'},target=/verification,readonly",
        "--mount",
        f"type=bind,source={reports},target=/reports",
        "-w",
        "/verification",
        "-e",
        "UV_PROJECT_ENVIRONMENT=/app/.venv",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "VIGIL_TEST_DATABASE_URL=" + database,
        "-e",
        "VIGIL_TEST_REDIS_URL=" + redis,
    ]
    if network:
        result += ["--network", network]
    if ca_file:
        path = Path(ca_file).resolve(strict=True)
        result += ["--mount", f"type=bind,source={path},target=/tmp/public-ca.pem,readonly"]
    return [*result, image, "sh", "-ec", TEST_COMMAND]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network")
    parser.add_argument("--ca-file")
    parser.add_argument("--image", default="vigil-api")
    args = parser.parse_args(argv)
    try:
        command = arguments(
            os.getenv("VIGIL_TEST_DATABASE_URL", ""),
            os.getenv("VIGIL_TEST_REDIS_URL", ""),
            network=args.network,
            ca_file=args.ca_file,
            image=args.image,
        )
    except Exception as error:
        print("backend_container_setup_failed:" + type(error).__name__)
        return 1
    return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
