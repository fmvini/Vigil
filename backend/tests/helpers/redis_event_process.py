"""Child EventHub used only by the real Pub/Sub process integration test."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from redis.asyncio import Redis  # noqa: E402

from app.services.events import EventHub  # noqa: E402


async def main():
    url, owner = sys.argv[1:]
    hub = EventHub(
        redis_factory=lambda: Redis.from_url(url, socket_connect_timeout=1, socket_timeout=2)
    )
    subscription = hub.subscribe(UUID(owner))
    try:
        async with asyncio.timeout(5):
            while not hub.connected:
                await asyncio.sleep(0.01)
        print(json.dumps({"ready": True}), flush=True)
        async with asyncio.timeout(10):
            payload = await subscription.queue.get()
        print(json.dumps(payload), flush=True)
    finally:
        await hub.close()


if __name__ == "__main__":
    asyncio.run(main())
