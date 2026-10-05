"""One bounded scheduler heartbeat per queue/group, independent of API probes."""

import hashlib
import json
import math

from redis.exceptions import RedisError

TTL_SECONDS = 120
STALE_SECONDS = 5
FIELDS = (
    "version",
    "last_attempt_ms",
    "last_success_ms",
    "outcome",
    "duration_ms",
    "scheduled_count",
    "published_count",
)
WRITE_SCRIPT = """
local t = redis.call('TIME')
local ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('HSET', KEYS[1], 'version', 1, 'last_attempt_ms', ms,
    'outcome', ARGV[1], 'duration_ms', ARGV[2])
if ARGV[1] == 'ok' then
    redis.call('HSET', KEYS[1], 'last_success_ms', ms,
        'scheduled_count', ARGV[3], 'published_count', ARGV[4])
end
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""


def scheduler_key(stream, group):
    identity = json.dumps([stream, group], ensure_ascii=True, separators=(",", ":"))
    return "vigil:heartbeat:scheduler:" + hashlib.sha256(identity.encode()).hexdigest()


async def write_scheduler_tick(
    redis, key, *, success, duration_ms, scheduled_count=None, published_count=None
):
    if (
        type(success) is not bool
        or type(duration_ms) not in (float, int)
        or not math.isfinite(duration_ms)
        or not 0 <= duration_ms <= 1e12
    ):
        raise ValueError("Invalid tick observation")
    if success and any(
        type(value) is not int or not 0 <= value <= 100
        for value in (scheduled_count, published_count)
    ):
        raise ValueError("Invalid tick counts")
    await redis.eval(
        WRITE_SCRIPT,
        1,
        key,
        "ok" if success else "error",
        round(duration_ms, 3),
        scheduled_count if success else "",
        published_count if success else "",
        TTL_SECONDS,
    )


def integer(value, maximum):
    if not isinstance(value, (str, bytes)) or len(value) > 16:
        raise ValueError("Invalid heartbeat integer")
    number = int(value)
    if not 0 <= number <= maximum:
        raise ValueError("Invalid heartbeat integer")
    return number


def seconds_since(timestamp, now):
    return None if timestamp is None or timestamp > now else round((now - timestamp) / 1000, 3)


async def scheduler_snapshot(redis, key):
    async with redis.pipeline(transaction=True) as reads:
        reads.time()
        reads.hmget(key, FIELDS)
        reads.pttl(key)
        clock, fields, ttl = await reads.execute(raise_on_error=False)
    for result in (clock, fields, ttl):
        if isinstance(result, RedisError):
            raise result
    if ttl == -2:
        return {
            "status": "ok",
            "heartbeat_state": "missing",
            "last_tick_age_seconds": None,
            "last_attempt_age_seconds": None,
        }
    try:
        version, attempted, succeeded, outcome, duration, scheduled, published = fields
        if (
            version not in (b"1", "1")
            or outcome not in (b"ok", "ok", b"error", "error")
            or not 0 <= ttl <= TTL_SECONDS * 1000
        ):
            raise ValueError("Invalid heartbeat schema")
        now = int(clock[0]) * 1000 + int(clock[1]) // 1000
        attempted = integer(attempted, 10**15)
        succeeded = None if succeeded is None else integer(succeeded, 10**15)
        if duration is None or len(duration) > 32:
            raise ValueError("Invalid heartbeat duration")
        duration = float(duration)
        if not math.isfinite(duration) or not 0 <= duration <= 1e12:
            raise ValueError("Invalid heartbeat duration")
        counts = (
            [None, None]
            if succeeded is None
            else [integer(scheduled, 100), integer(published, 100)]
        )
        outcome = outcome.decode("ascii") if isinstance(outcome, bytes) else outcome
        if outcome == "ok" and succeeded != attempted:
            raise ValueError("Invalid successful heartbeat")
    except (ValueError, TypeError):
        return {"status": "unavailable", "error_code": "scheduler_heartbeat_invalid"}
    success_age = seconds_since(succeeded, now)
    if attempted > now or (succeeded is not None and succeeded > attempted):
        state = "clock_skew"
    elif outcome == "error":
        state = "tick_failed"
    else:
        state = "fresh" if success_age <= STALE_SECONDS else "stale"
    return {
        "status": "ok",
        "heartbeat_state": state,
        "last_tick_age_seconds": success_age,
        "last_attempt_age_seconds": seconds_since(attempted, now),
        "last_attempt_outcome": outcome,
        "last_attempt_duration_ms": round(duration, 3),
        "last_success_scheduled_count": counts[0],
        "last_success_published_count": counts[1],
        "ttl_remaining_seconds": round(ttl / 1000, 3),
        "stale_after_seconds": STALE_SECONDS,
    }
