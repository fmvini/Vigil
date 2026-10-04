"""Real loopback Uvicorn replica with private stdin telemetry, isolated schema."""

import argparse
import asyncio
import json
import logging
import os
import re
import socket
import sys
import traceback
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db.session import create_engine  # noqa: E402
from app.main import create_app  # noqa: E402


def output(value):
    print(json.dumps(value), flush=True)


class ErrorProbe(logging.Handler):
    """Observe expected send deadlines without suppressing the real error log."""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.send_timeouts = self.unexpected = 0

    def emit(self, record):
        error = record.exc_info[1] if record.exc_info else None
        known = isinstance(error, TimeoutError) and any(
            frame.name == "bounded_send"
            and frame.filename.replace("\\", "/").endswith("/app/api/events.py")
            for frame in traceback.extract_tb(error.__traceback__)
        )
        if known:
            self.send_timeouts += 1
        else:
            self.unexpected += 1


async def run(schema, socket_buffer_bytes=0):
    assert re.fullmatch(r"vigil_test_[a-f0-9]{32}", schema)
    assert socket_buffer_bytes == 0 or 1024 <= socket_buffer_bytes <= 65536
    settings = Settings(
        database_url=os.environ["VIGIL_TEST_DATABASE_URL"],
        redis_url=os.environ["VIGIL_TEST_REDIS_URL"],
        allowed_origins=["http://vigil-qa.test"],
        environment="dev",
        pipeline_enabled=False,
        monitoring_network_enabled=False,
        _env_file=None,
    )
    engine = create_engine(
        settings.database_url,
        connect_args={"server_settings": {"search_path": schema, "timezone": "UTC"}},
    )
    app = create_app(settings, engine=engine)
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="error", access_log=False, timeout_graceful_shutdown=2)
    )
    errors = ErrorProbe()
    logging.getLogger("uvicorn.error").addHandler(errors)
    slow = {}
    with socket.socket() as listener:
        if socket_buffer_bytes:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, socket_buffer_bytes)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(15):
                while not server.started:
                    if task.done():
                        await task
                        raise RuntimeError("Replica exited before startup")
                    await asyncio.sleep(0.01)
            output({"ready": True, "port": port})
            while line := await asyncio.to_thread(sys.stdin.readline):
                command = json.loads(line)
                hub = app.state.event_hub
                if command["command"] == "slow":
                    owner = UUID(command["owner"])
                    assert owner not in slow
                    slow[owner] = hub.subscribe(owner)
                    output({"reserved": True})
                elif command["command"] == "stats":
                    output(
                        {
                            "connected": hub.connected,
                            "errors": {
                                "send_timeouts": errors.send_timeouts,
                                "unexpected": errors.unexpected,
                            },
                            "owners": {
                                str(owner): len(entries)
                                for owner, entries in hub.subscriptions.items()
                            },
                            "slow": {
                                str(owner): {
                                    "size": entry.queue.qsize(),
                                    "maxsize": entry.queue.maxsize,
                                }
                                for owner, entry in slow.items()
                            },
                            "transports": {
                                str(connection.client[1]): {
                                    "write_paused": connection.flow.write_paused,
                                    "buffered_bytes": connection.transport.get_write_buffer_size(),
                                }
                                for connection in server.server_state.connections
                                if connection.client is not None and connection.flow is not None
                            },
                        }
                    )
                elif command["command"] == "drain":
                    entry = slow[UUID(command["owner"])]
                    records = []
                    while not entry.queue.empty():
                        records.append(entry.queue.get_nowait())
                    output({"records": records})
                elif command["command"] == "drop":
                    hub.unsubscribe(slow.pop(UUID(command["owner"])))
                    output({"released": True})
                elif command["command"] == "stop":
                    break
                else:
                    raise ValueError("Unknown private telemetry command")
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 10)
            await engine.dispose()
    output({"closed": True, "subscriptions": len(app.state.event_hub.subscriptions)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--socket-buffer-bytes", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(run(args.schema, args.socket_buffer_bytes))
