"""Private, read-only operational snapshot. Does not start scheduler or workers."""

import asyncio
import json
from datetime import timedelta

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError, ResponseError
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db.models import CheckJob
from app.db.session import create_engine
from app.monitoring.heartbeat import scheduler_key, scheduler_snapshot

PEL_SAMPLE_LIMIT = 100
RECLAIM_IDLE_MS = 120_000
TIMEOUT_SECONDS = 3


def age(timestamp, now):
    return None if timestamp is None else round(max(0, (now - timestamp).total_seconds()), 3)


async def database_snapshot(engine, *, now=None):
    if engine.dialect.name != "postgresql":
        raise ValueError("Operational snapshot requires PostgreSQL")
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ValueError("Snapshot timestamp must be timezone-aware")
    async with engine.connect() as db, db.begin():
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        await db.execute(text("SET LOCAL statement_timeout = '3000ms'"))
        await db.execute(text("SET LOCAL lock_timeout = '1000ms'"))
        now = now or await db.scalar(select(func.clock_timestamp()))
        pending = CheckJob.status == "pending"
        running = CheckJob.status == "running"
        due = and_(
            pending,
            CheckJob.scheduled_at <= now,
            CheckJob.expires_at > now,
            or_(CheckJob.retry_at.is_(None), CheckJob.retry_at <= now),
        )
        lease_expired = and_(running, CheckJob.lease_expires_at <= now)
        predicates = {
            "pending_total": pending,
            "pending_due": due,
            "pending_retry_wait": and_(pending, CheckJob.retry_at > now, CheckJob.expires_at > now),
            "pending_unpublished_due": and_(due, CheckJob.published_at.is_(None)),
            "pending_republish_due": and_(
                due, CheckJob.published_at <= now - timedelta(seconds=30)
            ),
            "running_total": running,
            "running_lease_active": and_(running, CheckJob.lease_expires_at > now),
            "running_lease_expired": lease_expired,
            "expired_open": CheckJob.expires_at <= now,
        }
        result = await db.execute(
            select(
                *(
                    func.count().filter(predicate).label(name)
                    for name, predicate in predicates.items()
                ),
                func.min(CheckJob.scheduled_at).filter(due).label("oldest_due"),
                func.min(CheckJob.lease_expires_at).filter(lease_expired).label("oldest_lease"),
            ).where(CheckJob.status.in_(("pending", "running")))
        )
        row = result.one()._mapping
        return {
            "status": "ok",
            "observed_at": now.isoformat(),
            **{name: row[name] for name in predicates},
            "oldest_pending_due_age_seconds": age(row["oldest_due"], now),
            "oldest_expired_lease_age_seconds": age(row["oldest_lease"], now),
        }


async def redis_snapshot(redis, stream, group):
    # Atomic read commands avoid combining pre-ACK counts with post-ACK samples.
    # No IDLE filter: it could scan the entire PEL despite a small result limit.
    async with redis.pipeline(transaction=True) as reads:
        reads.xlen(stream)
        reads.xinfo_groups(stream)
        reads.xpending_range(stream, group, "-", "+", PEL_SAMPLE_LIMIT)
        length, groups, sample = await reads.execute(raise_on_error=False)
    if isinstance(length, RedisError):
        raise length
    if isinstance(groups, ResponseError) and str(groups) == "no such key":
        return {"status": "ok", "state": "stream_missing", "stream_length": 0}
    if isinstance(groups, RedisError):
        raise groups
    selected = next((item for item in groups if item["name"] in (group, group.encode())), None)
    if selected is None:
        return {"status": "ok", "state": "group_missing", "stream_length": length}
    if isinstance(sample, RedisError):
        raise sample
    pending = selected["pending"]
    return {
        "status": "ok",
        "state": "group_present",
        "stream_length": length,
        "consumers_registered": selected["consumers"],
        "pending_ack": pending,
        # Redis may report unknown lag; never replace it with stream_length.
        "undelivered_lag": selected.get("lag"),
        "pel_sample_size": len(sample),
        "pel_sample_limit": PEL_SAMPLE_LIMIT,
        "pel_sample_truncated": pending > len(sample),
        "pel_sample_max_idle_ms": max(
            (item["time_since_delivered"] for item in sample), default=None
        ),
        "pel_sample_redelivered": sum(item["times_delivered"] > 1 for item in sample),
        "pel_sample_reclaimable": sum(
            item["time_since_delivered"] >= RECLAIM_IDLE_MS for item in sample
        ),
        "reclaim_idle_threshold_ms": RECLAIM_IDLE_MS,
    }


async def component_snapshot(operation, error_code):
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            return await operation
    except (SQLAlchemyError, RedisError, TimeoutError, OSError):
        # Driver messages can contain connection strings, SQL or credentials.
        return {"status": "unavailable", "error_code": error_code}


async def snapshot(engine, redis, *, stream, group, pipeline_enabled, network_enabled):
    database, queue, scheduler = await asyncio.gather(
        component_snapshot(database_snapshot(engine), "database_unavailable"),
        component_snapshot(redis_snapshot(redis, stream, group), "redis_unavailable"),
        component_snapshot(
            scheduler_snapshot(redis, scheduler_key(stream, group)), "scheduler_unavailable"
        ),
    )
    return {
        "status": "ok"
        if database["status"] == queue["status"] == scheduler["status"] == "ok"
        else "partial",
        "pipeline_enabled": pipeline_enabled,
        "monitoring_network_enabled": network_enabled,
        "database": database,
        "queue": queue,
        "scheduler": scheduler,
    }


async def collect(settings):
    engine = create_engine(
        settings.database_url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=TIMEOUT_SECONDS,
        connect_args={"timeout": TIMEOUT_SECONDS, "command_timeout": TIMEOUT_SECONDS},
    )
    try:
        async with Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=TIMEOUT_SECONDS,
            socket_timeout=TIMEOUT_SECONDS,
            max_connections=2,
            retry=Retry(NoBackoff(), 0),
        ) as redis:
            return await snapshot(
                engine,
                redis,
                stream=settings.redis_stream_name,
                group=settings.redis_consumer_group,
                pipeline_enabled=settings.pipeline_enabled,
                network_enabled=settings.monitoring_network_enabled,
            )
    finally:
        await engine.dispose()


def main():
    try:
        report = asyncio.run(collect(Settings()))
    except (ValidationError, ValueError):
        report = {"status": "error", "error_code": "configuration_invalid"}
    except Exception:
        report = {"status": "error", "error_code": "snapshot_failed"}
    print(json.dumps(report, allow_nan=False, separators=(",", ":")))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
