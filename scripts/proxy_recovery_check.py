"""Move own Docker api alias between distinct live IPs; verify Nginx without reload."""

import argparse
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class ProxyRouteTimeout(TimeoutError):
    def __init__(self, observations):
        super().__init__("Proxy did not route to expected live API")
        self.observations = observations


class Docker:
    def command(self, *args, timeout=30):
        result = subprocess.run(
            ["docker", *map(str, args)], capture_output=True, text=True, timeout=timeout
        )
        if result.returncode:
            raise RuntimeError("Docker command failed: " + args[0])
        return result.stdout.strip()

    def inspect(self, kind, name):
        records = json.loads(self.command(kind, "inspect", name))
        if len(records) != 1:
            raise ValueError("Expected one own resource")
        return records[0]


def guard_network(record, token):
    if not record.get("Internal") or record.get("Labels", {}).get("vigil.qa.token") != token:
        raise ValueError("Refusing nonexclusive/noninternal proxy QA network")


def guard_container(record, token, network, *, allow_detached=False):
    if record.get("Config", {}).get("Labels", {}).get("vigil.qa.token") != token:
        raise ValueError("Refusing foreign proxy QA container")
    attached = set(record.get("NetworkSettings", {}).get("Networks", {}))
    if attached != {network} and not (allow_detached and not attached):
        raise ValueError("Proxy QA container has missing/foreign network")


def cleanup(docker, network, names, token):
    record = docker.inspect("network", network)
    guard_network(record, token)
    present = set(docker.command("container", "ls", "-a", "--format", "{{.Names}}").splitlines())
    owned = {}
    for name in names:
        if name in present:
            container = docker.inspect("container", name)
            guard_container(container, token, network, allow_detached=True)
            owned[container["Id"]] = name
    if set(record.get("Containers", {})) - set(owned):
        raise ValueError("Own network has unexpected endpoints; preserve for review")
    for name in owned.values():
        docker.command("container", "rm", "--force", name)
    record = docker.inspect("network", network)
    guard_network(record, token)
    if record.get("Containers"):
        raise ValueError("Own network gained an unexpected endpoint; preserve for review")
    docker.command("network", "rm", network)


def switch_alias(docker, network, old, new, token):
    guard_network(docker.inspect("network", network), token)
    records = [docker.inspect("container", name) for name in (old, new)]
    for record in records:
        guard_container(record, token, network)
    addresses = [record["NetworkSettings"]["Networks"][network]["IPAddress"] for record in records]
    if not all(addresses) or addresses[0] == addresses[1]:
        raise ValueError("Need two distinct own IPs")
    # Keep both listeners alive and their IPs fixed. Only move the api DNS alias.
    for name, address, alias in zip((old, new), addresses, ("qa-retired", "api"), strict=True):
        docker.command("network", "disconnect", network, name)
        docker.command("network", "connect", "--ip", address, "--alias", alias, network, name)
    return addresses


def get(docker, client, host, port=80, path="/health/ready"):
    code = (
        "import json,sys,urllib.request; "
        "u='http://'+sys.argv[1]+':'+sys.argv[2]+sys.argv[3]; "
        "r=urllib.request.urlopen(u,timeout=2); print(json.dumps(json.load(r)))"
    )
    return json.loads(docker.command("exec", client, "python", "-c", code, host, port, path))


def worker_pids(docker, container):
    output = docker.command("top", container, "-eo", "pid,args")
    pids = sorted(
        int(line.split()[0]) for line in output.splitlines() if "nginx: worker process" in line
    )
    if not pids:
        raise ValueError("Expected live Nginx workers in own proxy")
    return pids


def wait_get(docker, client, host, *, expected, port=80, path="/health/ready", seconds=12):
    started = time.monotonic()
    observations = []
    while time.monotonic() - started < seconds:
        try:
            data = get(docker, client, host, port, path)
            observations.append(data["version"])
            if data["version"] == expected:
                return round(time.monotonic() - started, 3), observations
        except RuntimeError:
            observations.append("unavailable")
        time.sleep(0.2)
    raise ProxyRouteTimeout(observations)


def probe(*, config=None, docker=None, api_image="vigil-api:latest", web_image="vigil-web:latest"):
    docker = docker or Docker()
    config = Path(config or ROOT / "frontend" / "nginx.conf").resolve()
    if not config.is_file():
        raise ValueError("Explicit Nginx configuration file missing")
    token = uuid4().hex
    network = "vigil-proxy-qa-" + token
    old, new, web = ("vigil-proxy-" + part + "-" + token for part in ("old", "new", "web"))
    report = {"token": token, "success": False, "cleanup": "not_created", "external_checks": False}
    created = False
    try:
        docker.command(
            "network", "create", "--internal", "--label", "vigil.qa.token=" + token, network
        )
        created = True
        guard_network(docker.inspect("network", network), token)
        for name, version in ((old, "original"), (new, "replacement")):
            arguments = [
                "run",
                "-d",
                "--name",
                name,
                "--label",
                "vigil.qa.token=" + token,
                "--network",
                network,
                "--user",
                "10001:10001",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--read-only",
                "--mount",
                f"type=bind,source={ROOT / 'infra' / 'web'},target=/qa,readonly",
                "-e",
                "VIGIL_PROXY_QA_VERSION=" + version,
            ]
            if name == old:
                arguments += ["--network-alias", "api"]
            docker.command(*arguments, "--entrypoint", "python", api_image, "/qa/qa_upstream.py")
        wait_get(docker, old, new, expected="replacement", port=8000)
        wait_get(docker, new, old, expected="original", port=8000)
        docker.command(
            "run",
            "-d",
            "--name",
            web,
            "--label",
            "vigil.qa.token=" + token,
            "--network",
            network,
            "--mount",
            f"type=bind,source={config},target=/etc/nginx/conf.d/default.conf,readonly",
            web_image,
        )
        wait_get(docker, new, web, expected="original")
        before = docker.inspect("container", web)
        workers_before = worker_pids(docker, web)
        old_ip, new_ip = switch_alias(docker, network, old, new, token)
        dns = json.loads(
            docker.command(
                "exec",
                old,
                "python",
                "-c",
                "import json,socket; print(json.dumps(sorted({a[4][0] for a in socket.getaddrinfo('api',8000,socket.AF_INET,socket.SOCK_STREAM)})))",
            )
        )
        assert dns == [new_ip]
        assert get(docker, new, old_ip, 8000)["version"] == "original"
        assert get(docker, old, new_ip, 8000)["version"] == "replacement"
        report.update(old_ip=old_ip, replacement_ip=new_ip, docker_dns=dns)
        elapsed, observations = wait_get(docker, old, web, expected="replacement")
        assert get(docker, old, web, path="/api/v1/qa")["version"] == "replacement"
        # Read first frame before fixture's five-second body completion: physical no buffering.
        stream_code = (
            "import json,sys,time,urllib.request; t=time.monotonic(); "
            "r=urllib.request.urlopen('http://'+sys.argv[1]+'/api/v1/events',timeout=2); "
            "event=r.readline(); data=r.readline(); r.close(); "
            "assert event==b'event: qa.ready\\n'; "
            "print(json.dumps({'data':json.loads(data[6:]),'first_frame_seconds':time.monotonic()-t}))"
        )
        stream = json.loads(docker.command("exec", old, "python", "-c", stream_code, web))
        assert stream["data"]["version"] == "replacement" and stream["first_frame_seconds"] < 2
        after = docker.inspect("container", web)
        assert before["State"]["Pid"] == after["State"]["Pid"]
        assert before["State"]["StartedAt"] == after["State"]["StartedAt"]
        assert worker_pids(docker, web) == workers_before
        report.update(
            success=True,
            recovery_seconds=elapsed,
            observations=observations,
            sse_first_frame_seconds=round(stream["first_frame_seconds"], 3),
            proxy_restart=False,
            worker_pids_unchanged=True,
        )
    except Exception as error:
        report.update(failure_type=type(error).__name__)
        if isinstance(error, ProxyRouteTimeout):
            report["observations"] = error.observations
    finally:
        if created:
            try:
                cleanup(docker, network, (old, new, web), token)
                report["cleanup"] = "confirmed"
            except Exception as error:
                report.update(
                    success=False, cleanup="pending_review", cleanup_failure=type(error).__name__
                )
        directory = ROOT / ".cache" / "proxy-qa" / token
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "report.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    return report, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nginx-config")
    args = parser.parse_args()
    report, path = probe(config=args.nginx_config)
    print(
        json.dumps(
            {"success": report["success"], "cleanup": report["cleanup"], "report": str(path)}
        )
    )
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
