"""Build/probe worker firewall in an exclusively owned internal Docker network."""

import argparse
import ipaddress
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class Docker:
    def __init__(self, *, run=subprocess.run):
        self.run = run

    def command(self, *arguments, timeout=60):
        result = self.run(
            ["docker", *map(str, arguments)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode:
            # Native output can contain deployment details. Keep report bounded/sanitized.
            raise RuntimeError("Docker command failed: " + arguments[0])
        return result.stdout.strip()

    def inspect(self, kind, name):
        records = json.loads(self.command(kind, "inspect", name))
        if len(records) != 1:
            raise ValueError("Expected exactly one exclusively owned Docker resource")
        return records[0]


def cleanup(docker, network, container, token, *, additional_containers=()):
    # Validate the whole resource set before the first removal. Never select by prefix.
    record = docker.inspect("network", network)
    if record.get("Labels", {}).get("vigil.qa.token") != token or not record.get("Internal"):
        raise ValueError("Refusing cleanup of a network without own UUID/internal guard")
    network_identifier = record.get("Id")
    if not isinstance(network_identifier, str) or not network_identifier:
        raise ValueError("Refusing cleanup with ambiguous network identity")
    names = docker.command("container", "ls", "-a", "--format", "{{.Names}}")
    present = [name for name in (container, *additional_containers) if name in names.splitlines()]
    owned = {}
    for name in present:
        candidate = docker.inspect("container", name)
        if candidate.get("Config", {}).get("Labels", {}).get("vigil.qa.token") != token:
            raise ValueError("Refusing cleanup of a container without own UUID label")
        if set(candidate.get("NetworkSettings", {}).get("Networks", {})) != {network}:
            raise ValueError("Refusing cleanup of a container with missing/foreign network")
        identifier = candidate.get("Id")
        if not isinstance(identifier, str) or not identifier or identifier in owned:
            raise ValueError("Refusing cleanup with ambiguous container identity")
        owned[identifier] = name
    if set(record.get("Containers", {})) - set(owned):
        raise ValueError("Own network has unexpected endpoints; preserve all resources for review")
    for identifier, name in owned.items():
        candidate = docker.inspect("container", name)
        if (
            candidate.get("Id") != identifier
            or candidate.get("Config", {}).get("Labels", {}).get("vigil.qa.token") != token
            or set(candidate.get("NetworkSettings", {}).get("Networks", {})) != {network}
        ):
            raise ValueError("Own container changed during cleanup; preserve it for review")
        docker.command("container", "rm", "--force", identifier)
    record = docker.inspect("network", network)
    if (
        record.get("Id") != network_identifier
        or record.get("Labels", {}).get("vigil.qa.token") != token
        or not record.get("Internal")
    ):
        raise ValueError("Refusing cleanup of a network without own UUID/internal guard")
    if record.get("Containers"):
        raise ValueError("Own network has unexpected endpoints; cleanup pending review")
    docker.command("network", "rm", network_identifier)


def probe(docker, *, image="vigil-worker-egress:qa"):
    token = uuid4().hex
    network, container = "vigil-egress-qa-" + token, "vigil-egress-probe-" + token
    created = False
    report = {
        "token": token,
        "network": network,
        "container": container,
        "success": False,
    }
    try:
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
        record = docker.inspect("network", network)
        if (
            record["Labels"].get("vigil.qa.token") != token
            or not record["Internal"]
            or not record["EnableIPv6"]
        ):
            raise ValueError("QA network ownership/isolation mismatch")
        output = docker.command(
            "run",
            "--rm",
            "--name",
            container,
            "--label",
            "vigil.qa.token=" + token,
            "--network",
            network,
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
            "--read-only",
            "--tmpfs",
            "/tmp:size=32m,mode=1777",
            "--mount",
            f"type=bind,source={ROOT / 'infra' / 'worker'},target=/qa,readonly",
            "-e",
            "VIGIL_EGRESS_QA_TOKEN=" + token,
            "-e",
            "VIGIL_QA_CONTAINER=" + container,
            "-e",
            "VIGIL_PIPELINE_ENABLED=false",
            "-e",
            "VIGIL_MONITORING_NETWORK_ENABLED=false",
            "--entrypoint",
            "python",
            image,
            "/qa/qa_probe.py",
            timeout=50,
        )
        report["probe"] = json.loads(output)
        expected = report["probe"]
        if (
            expected["blocked"] != 18
            or len(expected["allowed"]) != 6
            or expected["uid"] != 10001
            or expected["capabilities"] != 0
            or expected["dns"] != "internal_resolved"
        ):
            raise ValueError("Incomplete physical socket/privilege proof")
        # Probe the actual image entrypoint too, using only literal synthetic control IPs.
        output = docker.command(
            "run",
            "--rm",
            "--name",
            container,
            "--label",
            "vigil.qa.token=" + token,
            "--network",
            network,
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
            "--read-only",
            "-e",
            "VIGIL_DATABASE_URL=postgresql+asyncpg://qa:synthetic@192.168.240.11:5432/qa",
            "-e",
            "VIGIL_REDIS_URL=redis://192.168.240.12:6379/0",
            image,
            "python",
            "-c",
            "import os; from pathlib import Path; assert os.getuid()==os.getgid()==10001; "
            "assert int(next(x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('CapEff:')).split(':')[1],16)==0; print('entrypoint_dropped')",
            timeout=20,
        )
        if output != "entrypoint_dropped":
            raise ValueError("Worker entrypoint did not drop privileges")
        report["entrypoint"] = "dropped"
        output = docker.command(
            "run",
            "--rm",
            "--name",
            container,
            "--label",
            "vigil.qa.token=" + token,
            "--network",
            network,
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
            "--read-only",
            "--tmpfs",
            "/tmp:size=32m,mode=1777",
            "--mount",
            f"type=bind,source={ROOT / 'infra' / 'worker'},target=/qa,readonly",
            "--mount",
            f"type=bind,source={ROOT / 'backend' / 'tests' / 'fixtures' / 'tls'},target=/fixtures,readonly",
            "-e",
            "VIGIL_EGRESS_QA_TOKEN=" + token,
            "-e",
            "VIGIL_PIPELINE_ENABLED=false",
            "-e",
            "VIGIL_MONITORING_NETWORK_ENABLED=false",
            "--entrypoint",
            "python",
            image,
            "/qa/qa_tls_probe.py",
            timeout=40,
        )
        tls = json.loads(output)
        if (
            tls.get("cases")
            != {
                "ipv4": "verified",
                "ipv6": "verified",
                "untrusted_ca": "tls_error",
                "wrong_hostname": "tls_error",
                "mixed_dns": "blocked_destination",
                "private_dns": "blocked_destination",
            }
            or tls.get("http_requests") != 2
            or not tls.get("sni_verified")
            or not tls.get("headers_only")
            or tls.get("pinned_peer") != "real_public_alias"
            or tls.get("uid") != 10001
        ):
            raise ValueError("Incomplete default transport/TLS proof under firewall")
        report["tls"] = tls
        report["success"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
    finally:
        if created:
            try:
                cleanup(docker, network, container, token)
                report["cleanup"] = "confirmed"
            except Exception as error:
                report["cleanup"] = "pending_review"
                report["cleanup_error_type"] = type(error).__name__
                report["success"] = False
    return report


def ndp_probe(docker, *, image="vigil-worker-egress:qa"):
    token = uuid4().hex
    network, peer, worker = (
        "vigil-egress-" + suffix + "-" + token for suffix in ("ndp", "peer", "client")
    )
    # Narrow, randomly numbered global-unicast QA prefix. Docker internal provides
    # no external forwarding; this is a fixture, not an assertion of IP ownership
    # or Internet availability. Public aliases outside an internal prefix cannot
    # cross that bridge's isolation filter.
    prefix = ipaddress.IPv6Address(
        "3000:" + ":".join(token[start : start + 4] for start in (0, 4, 8)) + "::"
    ).compressed
    subnet, target = prefix + "/124", prefix + "1"
    report = {"token": token, "network": network, "target": target, "success": False}
    created = False

    def arguments(name, address):
        return [
            "--name",
            name,
            "--label",
            "vigil.qa.token=" + token,
            "--network",
            network,
            "--ip6",
            address,
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
            "--read-only",
            "--tmpfs",
            "/tmp:size=32m,mode=1777",
            "--mount",
            f"type=bind,source={ROOT / 'infra' / 'worker'},target=/qa,readonly",
            "--mount",
            f"type=bind,source={ROOT / 'backend' / 'tests' / 'fixtures' / 'tls'},target=/fixtures,readonly",
            "-e",
            "VIGIL_EGRESS_QA_TOKEN=" + token,
            "-e",
            "VIGIL_QA_TARGET6=" + target,
            "-e",
            "VIGIL_PIPELINE_ENABLED=false",
            "-e",
            "VIGIL_MONITORING_NETWORK_ENABLED=false",
            "--entrypoint",
            "python",
        ]

    try:
        docker.command(
            "network",
            "create",
            "--internal",
            "--ipv6",
            "--subnet",
            subnet,
            "--gateway",
            prefix + "e",
            "--label",
            "vigil.qa.token=" + token,
            network,
        )
        created = True
        record = docker.inspect("network", network)
        if (
            record["Labels"].get("vigil.qa.token") != token
            or not record["Internal"]
            or not record["EnableIPv6"]
            or subnet not in {entry["Subnet"] for entry in record["IPAM"]["Config"]}
        ):
            raise ValueError("NDP network ownership/prefix/isolation mismatch")
        docker.command("run", "-d", *arguments(peer, target), image, "/qa/qa_ndp_probe.py", "peer")
        record = docker.inspect("container", peer)
        if (
            record["Config"]["Labels"].get("vigil.qa.token") != token
            or set(record["NetworkSettings"]["Networks"]) != {network}
            or record["NetworkSettings"]["Networks"][network]["GlobalIPv6Address"] != target
            or not record["State"]["Running"]
        ):
            raise ValueError("NDP peer ownership/address/namespace mismatch")
        deadline = time.monotonic() + 10
        while True:
            lines = docker.command("logs", peer).splitlines()
            if lines and json.loads(lines[0]) == {"ready": True, "uid": 10001}:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Own NDP peer did not become ready")
            time.sleep(0.1)
        result = json.loads(
            docker.command(
                "run",
                "--rm",
                *arguments(worker, prefix + "2"),
                image,
                "/qa/qa_ndp_probe.py",
                "client",
                timeout=40,
            )
        )
        if (
            result.get("ndp_denied") != "timeout"
            or result.get("denied_solicitations", 0) < 1
            or result.get("accepted_neighbor_messages", 0) < 1
            or result.get("accepted_neighbor_messages")
            != result.get("accepted_solicitations", 0) + result.get("accepted_advertisements", 0)
            or result.get("neighbor") != "resolved_on_eth0"
            or result.get("tls") != "verified"
            or result.get("pinned_peer") != "own_global_unicast_peer"
            or result.get("uid") != 10001
        ):
            raise ValueError("Incomplete physical NDP dependency/TLS proof")
        if docker.command("wait", peer, timeout=15) != "0":
            raise ValueError("Own TLS peer failed")
        lines = docker.command("logs", peer).splitlines()
        if len(lines) != 2 or json.loads(lines[1]) != {
            "http_requests": 1,
            "sni_verified": True,
            "headers_only": True,
            "uid": 10001,
        }:
            raise ValueError("Incomplete peer-side NDP/TLS proof")
        report["probe"] = result
        report["success"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
    finally:
        if created:
            try:
                cleanup(docker, network, worker, token, additional_containers=(peer,))
                report["cleanup"] = "confirmed"
            except Exception as error:
                report["cleanup"] = "pending_review"
                report["cleanup_error_type"] = type(error).__name__
                report["success"] = False
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--image", default="vigil-worker-egress:qa")
    args = parser.parse_args(argv)
    docker = Docker()
    if args.build:
        docker.command("build", "--tag", args.image, ROOT / "infra" / "worker", timeout=300)
    report = probe(docker, image=args.image)
    if report["success"]:
        report["ndp"] = ndp_probe(docker, image=args.image)
        report["success"] = report["ndp"]["success"]
        if report["ndp"].get("cleanup") != "confirmed":
            report["cleanup"] = "pending_review"
    directory = ROOT / ".cache" / "egress-qa" / report["token"]
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "success": report["success"],
                "cleanup": report.get("cleanup"),
                "report": str(path),
            }
        )
    )
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
