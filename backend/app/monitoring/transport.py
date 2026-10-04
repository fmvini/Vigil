"""HTTP/1.1 transport that resolves once and connects only to validated public IPs.

DNS validation happens at every new connection. HTTP origin/Host/TLS SNI retain the
original hostname; connections and cookies are not shared between attempts.
"""

import asyncio
import ipaddress
import socket
import ssl
from collections.abc import Awaitable, Callable

import certifi
import httpcore
import httpx

from app.domain.monitors import validate_url


class BlockedDestination(Exception):
    """Policy/internal error: never a target availability failure."""


class DNSFailure(Exception):
    def __init__(self, message, *, transient=True):
        self.transient = transient
        super().__init__(message)


class HeaderLimitExceeded(Exception):
    pass


def public_address(value: str) -> str:
    if "%" in value:
        raise BlockedDestination("Scoped address forbidden")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise BlockedDestination("Invalid address") from None
    if (
        not address.is_global
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or isinstance(address, ipaddress.IPv6Address)
        and (
            address.ipv4_mapped is not None
            or address.sixtofour is not None
            or address.teredo is not None
            or address in ipaddress.ip_network("64:ff9b::/96")
            or address in ipaddress.ip_network("64:ff9b:1::/48")
        )
    ):
        raise BlockedDestination("Non-public address forbidden")
    return address.compressed


async def resolve_addresses(host: str, port: int) -> list[str]:
    try:
        results = await asyncio.get_running_loop().getaddrinfo(
            host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as exc:
        raise DNSFailure("DNS resolution failed", transient=exc.errno == socket.EAI_AGAIN) from None
    return list(dict.fromkeys(entry[4][0] for entry in results))


class HeaderGuardStream(httpcore.AsyncNetworkStream):
    def __init__(self, stream, *, max_header_bytes=32768):
        self.stream = stream
        self.max_header_bytes = max_header_bytes
        self.buffer = bytearray()
        self.header_bytes = 0
        self.final_headers = False

    async def read(self, max_bytes, timeout=None):
        # At most 4KiB may accompany the final headers; no body reads are requested.
        data = await self.stream.read(min(max_bytes, 4096), timeout=timeout)
        if not self.final_headers:
            self.buffer.extend(data)
            while not self.final_headers:
                end = self.buffer.find(b"\r\n\r\n")
                if end < 0:
                    if self.header_bytes + len(self.buffer) > self.max_header_bytes:
                        raise HeaderLimitExceeded("Response headers too large")
                    break
                end += 4
                self.header_bytes += end
                if self.header_bytes > self.max_header_bytes:
                    raise HeaderLimitExceeded("Response headers too large")
                status_line = bytes(self.buffer).split(b"\r\n", 1)[0].split(b" ")
                # Interim responses are included in the aggregate cap.
                interim = len(status_line) >= 2 and status_line[1].startswith(b"1")
                del self.buffer[:end]
                if not interim:
                    self.final_headers = True
                    self.buffer.clear()
        return data

    async def write(self, buffer, timeout=None):
        await self.stream.write(buffer, timeout=timeout)

    async def aclose(self):
        await self.stream.aclose()

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        stream = await self.stream.start_tls(
            ssl_context, server_hostname=server_hostname, timeout=timeout
        )
        return HeaderGuardStream(stream, max_header_bytes=self.max_header_bytes)

    def get_extra_info(self, info):
        return self.stream.get_extra_info(info)


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        *,
        resolver: Callable[..., Awaitable[list[str]]] = resolve_addresses,
        backend=None,
        dns_timeout=3.0,
    ):
        self.resolver = resolver
        self.backend = backend or httpcore.AnyIOBackend()
        self.dns_timeout = dns_timeout

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if port not in {80, 443}:
            raise BlockedDestination("Port forbidden")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            try:
                async with asyncio.timeout(min(self.dns_timeout, timeout or self.dns_timeout)):
                    resolved = await self.resolver(host, port)
            except TimeoutError:
                raise DNSFailure("DNS deadline exceeded") from None
        else:
            resolved = [str(literal)]
        if not resolved or len(resolved) > 32:
            raise BlockedDestination("Invalid DNS response")
        # Validate EVERY A/AAAA before any socket; mixed public/private answers fail closed.
        addresses = [public_address(value) for value in resolved]
        address = addresses[0]
        stream = await self.backend.connect_tcp(
            address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
        peer = stream.get_extra_info("server_addr")
        try:
            if peer is None or public_address(peer[0]) != address or peer[1] != port:
                raise BlockedDestination("Connected peer differs from validated destination")
        except BaseException:
            await stream.aclose()
            raise
        return HeaderGuardStream(stream)

    async def connect_unix_socket(self, *args, **kwargs):
        raise BlockedDestination("Unix sockets forbidden")

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


class CoreResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        async for chunk in self.stream:
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class SafeTransport(httpx.AsyncBaseTransport):
    def __init__(self, *, backend=None):
        # Default context verifies CA and hostname; trust_env cannot alter this transport.
        self.pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(cafile=certifi.where()),
            network_backend=backend or PinnedNetworkBackend(),
            max_connections=1,
            max_keepalive_connections=0,
            retries=0,
            http1=True,
            http2=False,
        )

    async def handle_async_request(self, request):
        try:
            validate_url(str(request.url))
        except ValueError:
            raise BlockedDestination("Invalid destination URL") from None
        if request.method != "GET":
            raise BlockedDestination("Only GET is permitted")
        extensions = {key: value for key, value in request.extensions.items() if key == "timeout"}
        core_request = httpcore.Request(
            method="GET",
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=extensions,
        )
        response = await self.pool.handle_async_request(core_request)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=CoreResponseStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self):
        await self.pool.aclose()
