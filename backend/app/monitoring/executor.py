import asyncio
import random
import ssl
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpcore
import httpx

from app.monitoring.transport import (
    BlockedDestination,
    DNSFailure,
    HeaderLimitExceeded,
    SafeTransport,
)
from app.security import utcnow
from app.services.check_jobs import ClaimedJob, EvaluatedCycle


class OperationalError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def is_tls_error(exc):
    while exc is not None:
        if isinstance(exc, ssl.SSLError):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


class ConcurrencyLimits:
    def __init__(self, *, global_limit=50, host_limit=5, acquire_timeout=1.0):
        self.global_slots = asyncio.Semaphore(global_limit)
        self.host_limit = host_limit
        self.hosts = {}
        self.acquire_timeout = acquire_timeout

    @asynccontextmanager
    async def slot(self, host):
        # Map entry refs include both waiters and holders; cleanup keeps memory bounded.
        semaphore, refs = self.hosts.get(host, (asyncio.Semaphore(self.host_limit), 0))
        self.hosts[host] = (semaphore, refs + 1)
        host_acquired = global_acquired = False
        try:
            async with asyncio.timeout(self.acquire_timeout):
                await semaphore.acquire()
                host_acquired = True
                await self.global_slots.acquire()
                global_acquired = True
            yield
        except TimeoutError:
            if not global_acquired:
                raise OperationalError("pool_exhausted") from None
            raise
        finally:
            if global_acquired:
                self.global_slots.release()
            if host_acquired:
                semaphore.release()
            current_semaphore, refs = self.hosts[host]
            if refs == 1:
                del self.hosts[host]
            else:
                self.hosts[host] = (current_semaphore, refs - 1)


class CheckExecutor:
    def __init__(
        self, *, transport_factory=SafeTransport, limits=None, sleep=asyncio.sleep, jitter=None
    ):
        self.transport_factory = transport_factory
        self.limits = limits or ConcurrencyLimits()
        self.sleep = sleep
        self.jitter = jitter or (lambda delay: random.uniform(delay * 0.8, delay * 1.2))

    async def run(self, claim: ClaimedJob) -> EvaluatedCycle:
        config = claim.config_snapshot
        host = urlsplit(config["url"]).hostname
        async with self.limits.slot(host):
            # Pool waiting is not attributed to the target and cannot shrink its timeout.
            now = utcnow()
            remaining = (min(claim.expires_at, claim.lease_expires_at) - now).total_seconds()
            if remaining < claim.budget_ms / 1000:
                raise OperationalError("execution_crashed")
            try:
                async with asyncio.timeout(min(claim.budget_ms / 1000, 55.0)):
                    return await self._cycle(config)
            except TimeoutError:
                raise OperationalError("execution_crashed") from None

    async def _cycle(self, config):
        started_at = utcnow()
        cycle_start = time.monotonic()
        attempts = []
        for number in range(config["retry_count"] + 1):
            status = latency = error = None
            transient = True
            attempt_start = time.monotonic()
            try:
                timeout = config["timeout_ms"] / 1000
                async with asyncio.timeout(timeout):
                    async with httpx.AsyncClient(
                        transport=self.transport_factory(),
                        trust_env=False,
                        follow_redirects=False,
                        timeout=timeout,
                        headers={"User-Agent": "Vigil/0.1", "Accept-Encoding": "identity"},
                    ) as client:
                        async with client.stream("GET", config["url"]) as response:
                            status = response.status_code
                            latency = (time.monotonic() - attempt_start) * 1000
                            if not 200 <= status <= 599:
                                raise HeaderLimitExceeded("Invalid final HTTP response")
                            if status != config["expected_status"]:
                                error = "unexpected_status"
                            # Do not iterate/read response body. Close immediately after headers.
            except (BlockedDestination, HeaderLimitExceeded):
                raise OperationalError("blocked_destination") from None
            except (httpcore.PoolTimeout, httpx.PoolTimeout):
                raise OperationalError("pool_exhausted") from None
            except DNSFailure as exc:
                error = "dns_error"
                transient = exc.transient
            except (TimeoutError, httpcore.TimeoutException, httpx.TimeoutException):
                error = "timeout"
            except (
                httpcore.NetworkError,
                httpx.NetworkError,
                httpcore.ProtocolError,
                httpx.ProtocolError,
            ) as exc:
                error = "tls_error" if is_tls_error(exc) else "connection_error"
                if isinstance(exc, (httpcore.ProtocolError, httpx.ProtocolError)):
                    transient = False
            duration = (time.monotonic() - attempt_start) * 1000
            attempts.append(
                {
                    "http_status": status,
                    "error_code": error,
                    "latency_ms": latency,
                    "duration_ms": duration,
                }
            )
            retry = (
                transient
                and error in {"timeout", "connection_error", "dns_error"}
                or (error == "unexpected_status" and status >= 500)
            )
            if not retry or number >= config["retry_count"]:
                break
            await self.sleep(self.jitter((0.5, 1.0)[number]))
        return EvaluatedCycle(
            started_at=started_at,
            completed_at=utcnow(),
            outcome="success" if error is None else "failure",
            http_status=status,
            latency_ms=latency,
            cycle_duration_ms=(time.monotonic() - cycle_start) * 1000,
            attempt_count=len(attempts),
            attempts=attempts,
            error_code=error,
        )
