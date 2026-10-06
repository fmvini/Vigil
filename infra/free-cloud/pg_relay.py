"""Trusted TCP passthrough to one configured public PostgreSQL session pooler.

No TLS termination: asyncpg verifies the original hostname and certificate.
Runs on an ephemeral bridge without published ports or database credentials.
"""

import asyncio
import ipaddress
import os
import re
import socket

POOLER = re.compile(r"ep-[a-z0-9-]+\.(?:[a-z0-9-]+\.)*neon\.tech\Z")


def validate_addresses(values):
    if not values or len(values) > 8 or any(not ipaddress.ip_address(v).is_global for v in values):
        raise ValueError("Pooler must resolve exclusively to public addresses")
    return sorted(set(values))


async def addresses(host, *, resolver=None):
    if not isinstance(host, str) or not POOLER.fullmatch(host):
        raise ValueError("Expected the configured Neon PostgreSQL hostname")
    resolver = resolver or asyncio.get_running_loop().getaddrinfo
    records = await resolver(host, 5432, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    return validate_addresses(sorted({record[4][0] for record in records}))


async def pipe(reader, writer):
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()


async def relay(reader, writer, *, targets):
    upstream_writer = None
    try:
        for target in targets:
            try:
                upstream_reader, upstream_writer = await asyncio.wait_for(
                    asyncio.open_connection(target, 5432), timeout=5
                )
                break
            except (OSError, TimeoutError):
                continue
        if upstream_writer is None:
            return
        tasks = {
            asyncio.create_task(pipe(reader, upstream_writer)),
            asyncio.create_task(pipe(upstream_reader, writer)),
        }
        try:
            async with asyncio.timeout(120):
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except (OSError, TimeoutError):
        pass
    finally:
        writer.close()
        if upstream_writer:
            upstream_writer.close()


async def main():
    if not POOLER.fullmatch(os.environ.get("VIGIL_POOLER_HOST", "")):
        raise ValueError("Invalid configured database hostname")
    # Upstream DNS was resolved by the trusted orchestrator before creating the
    # Docker alias; resolving that name here would point back to this relay.
    targets = validate_addresses(os.environ.get("VIGIL_POOLER_ADDRESSES", "").split(","))
    server = await asyncio.start_server(lambda r, w: relay(r, w, targets=targets), "0.0.0.0", 5432)
    print("pooler_relay_ready", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print("pooler_relay_failed:" + type(error).__name__, flush=True)
        raise SystemExit(1) from None
