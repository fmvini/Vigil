"""Real loopback Uvicorn replica with private stdin telemetry, isolated schema."""

import argparse
import asyncio
import json
import os
import re
import socket
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db.session import create_engine  # noqa: E402
from app.main import create_app  # noqa: E402


def output(value):
    print(json.dumps(value), flush=True)


async def run(schema):
    assert re.fullmatch(r"vigil_test_[a-f0-9]{32}", schema)
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
    slow = {}
    with socket.socket() as listener:
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
    args = parser.parse_args()
    asyncio.run(run(args.schema))
