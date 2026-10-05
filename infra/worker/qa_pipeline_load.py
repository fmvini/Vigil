"""Real TLS load fixture in an exclusively owned worker network namespace."""

import argparse
import concurrent.futures
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path

import egress

PUBLIC = "93.184.216.34"
HOST = "sockets.example.com"
FIXTURES = Path("/fixtures")


class ControlledFailure(Exception):
    def __init__(self, observation):
        super().__init__("controlled_helper_failed")
        self.observation = observation


def unprivileged():
    assert os.getuid() == os.getgid() == 10001
    assert all(
        int(line.split(":", 1)[1], 16) == 0
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith("Cap")
    )


def serve(args):
    unprivileged()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(FIXTURES / "server.pem", FIXTURES / "server.key.pem")
    names, requests, closed, errors = [], [], [], []
    lock = threading.Lock()

    def sni(connection, name, selected_context):
        with lock:
            names.append(name)

    context.set_servername_callback(sni)

    def handle(connection):
        connection.settimeout(5)
        try:
            with context.wrap_socket(connection, server_side=True) as secured:
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = secured.recv(4096)
                    assert chunk and len(request) + len(chunk) <= 32768
                    request += chunk
                assert request.startswith(b"GET /health HTTP/1.1\r\n")
                assert b"Host: sockets.example.com\r\n" in request
                with lock:
                    requests.append(True)
                time.sleep(0.02)
                secured.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 9999999\r\n\r\n")
                assert secured.recv(1) == b""
                with lock:
                    closed.append(True)
        except Exception as error:
            with lock:
                errors.append(type(error).__name__)
        finally:
            connection.close()

    listener = socket.socket(fileno=int(os.environ["VIGIL_QA_LISTENER_FD"]))
    listener.settimeout(args.duration_seconds + args.drain_timeout_seconds + 30)
    print(json.dumps({"ready": True, "uid": 10001, "capabilities": 0}), flush=True)
    with listener, concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(handle, listener.accept()[0]) for _ in range(args.jobs)]
        for future in futures:
            future.result()
    assert len(names) == len(requests) == len(closed) == args.jobs and not errors
    assert all(name == HOST for name in names)
    print(
        json.dumps(
            {
                "http_requests": len(requests),
                "closed_after_headers": len(closed),
                "sni_verified": True,
                "host_verified": True,
                "headers_only": True,
                "synthetic_response_delay_ms": 20,
                "uid": 10001,
                "capabilities": 0,
            }
        ),
        flush=True,
    )


def run(args):
    args.failure_stage = "namespace"
    assert os.getuid() == 0
    assert Path("/.dockerenv").is_file()
    assert "nameserver 127.0.0.11" in Path("/etc/resolv.conf").read_text()
    args.failure_stage = "alias"
    subprocess.run(
        ["ip", "address", "add", PUBLIC + "/32", "dev", "lo"],
        check=True,
        capture_output=True,
        timeout=10,
    )
    args.failure_stage = "listener"
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((PUBLIC, 443))
    listener.listen(100)
    try:
        args.failure_stage = "firewall"
        egress.install(egress.control_endpoints(os.environ))
        listener.set_inheritable(True)
        os.environ["VIGIL_QA_LISTENER_FD"] = str(listener.fileno())
        command = egress.dropped_command(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "manager",
                "--run-id",
                args.run_id,
                "--jobs",
                str(args.jobs),
                "--duration-seconds",
                str(args.duration_seconds),
                "--callback-limit",
                str(args.callback_limit),
                "--drain-timeout-seconds",
                str(args.drain_timeout_seconds),
            ]
        )
        # Supervisor and its children share UID10001/caps0, including failure cleanup.
        args.failure_stage = "manager_exec"
        os.execvpe(command[0], command, os.environ)
    finally:
        listener.close()


def manage(args):
    unprivileged()
    listener = socket.socket(fileno=int(os.environ["VIGIL_QA_LISTENER_FD"]))
    arguments = [
        "--run-id",
        args.run_id,
        "--jobs",
        str(args.jobs),
        "--duration-seconds",
        str(args.duration_seconds),
        "--callback-limit",
        str(args.callback_limit),
        "--drain-timeout-seconds",
        str(args.drain_timeout_seconds),
    ]
    server = None
    try:
        args.failure_stage = "server_spawn"
        server = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "server", *arguments],
            env={**os.environ, "VIGIL_QA_LISTENER_FD": str(listener.fileno())},
            pass_fds=(listener.fileno(),),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        listener.close()
        # The server reports readiness only after validating its UID and all capabilities.
        args.failure_stage = "server_ready"
        ready = server.stdout.readline()
        assert json.loads(ready) == {"ready": True, "uid": 10001, "capabilities": 0}
        args.failure_stage = "worker_spawn"
        worker = subprocess.run(
            [
                sys.executable,
                "/app/tests/helpers/pipeline_load_process.py",
                *arguments,
                "--ca-file",
                str(FIXTURES / "ca.pem"),
            ],
            capture_output=True,
            text=True,
            timeout=args.duration_seconds + args.drain_timeout_seconds + 45,
        )
        helper = json.loads(worker.stdout)
        if worker.returncode != 0:
            raise ControlledFailure(helper)
        args.failure_stage = "server_result"
        output, error = server.communicate(timeout=10)
        assert server.returncode == 0 and not error, "Controlled TLS fixture failed"
        print(json.dumps({"pipeline": helper, "tls": json.loads(output)}))
    finally:
        listener.close()
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.communicate(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=["run", "server", "manager"], default="run")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--jobs", type=int, default=100)
    parser.add_argument("--duration-seconds", type=float, default=60)
    parser.add_argument("--callback-limit", type=int, default=50)
    parser.add_argument("--drain-timeout-seconds", type=float, default=30)
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{32}", args.run_id)
    assert args.run_id == os.environ.get("VIGIL_EGRESS_QA_TOKEN")
    assert os.environ.get("VIGIL_TEST_PIPELINE_LOAD_QA") == "1"
    assert os.environ.get("VIGIL_PIPELINE_ENABLED") == "false"
    assert os.environ.get("VIGIL_MONITORING_NETWORK_ENABLED") == "false"
    assert 1 <= args.jobs <= 2000 and 0 <= args.duration_seconds <= 600
    assert 1 <= args.callback_limit <= 50 and 1 <= args.drain_timeout_seconds <= 120
    try:
        if args.mode == "server":
            serve(args)
        elif args.mode == "manager":
            manage(args)
        else:
            run(args)
    except Exception as error:
        diagnostic = (
            {"pipeline": error.observation}
            if isinstance(error, ControlledFailure)
            else {
                "failure_code": "fixture_"
                + getattr(args, "failure_stage", "server")
                + "_"
                + type(error).__name__.lower()
            }
        )
        print(json.dumps(diagnostic), flush=True)
        print("pipeline_load_fixture_failed:" + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
