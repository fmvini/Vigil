from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import CheckJob
from app.monitoring.publisher import publish_pending
from app.security import utcnow
from app.services.check_jobs import schedule_due


async def test_publisher_republishes_without_holding_transaction(api_app, monitor):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("Publisher requires PostgreSQL clock/transactions")
    factory = api_app.state.session_factory
    timestamp = utcnow()
    async with factory.begin() as db:
        identifiers = await schedule_due(db, now=timestamp)
    sent = []

    async def publish(identifier):
        # Independent session demonstrates no publisher row lock/transaction during send.
        async with factory() as db:
            assert len((await db.scalars(select(CheckJob))).all()) == 1
        sent.append(identifier)

    assert await publish_pending(factory, publish, now=timestamp) == 1
    assert await publish_pending(factory, publish, now=timestamp + timedelta(seconds=29)) == 0
    assert await publish_pending(factory, publish, now=timestamp + timedelta(seconds=31)) == 1
    assert sent == [str(identifiers[0])] * 2


async def test_publish_failure_leaves_pending_for_recovery(api_app, monitor):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("Publisher requires PostgreSQL clock/transactions")
    factory = api_app.state.session_factory
    async with factory.begin() as db:
        identifiers = await schedule_due(db)

    async def fail(identifier):
        raise RuntimeError("simulated broker failure")

    with pytest.raises(RuntimeError):
        await publish_pending(factory, fail)
    async with factory() as db:
        job = await db.get(CheckJob, identifiers[0])
        assert job.status == "pending" and job.published_at is None


async def test_publication_mark_does_not_overwrite_new_technical_retry(api_app, monitor):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("Publisher requires PostgreSQL clock/transactions")
    factory = api_app.state.session_factory
    async with factory.begin() as db:
        identifiers = await schedule_due(db)

    async def publication_race(identifier):
        async with factory.begin() as db:
            job = await db.get(CheckJob, identifiers[0])
            job.execution_count = 1
            job.retry_at = utcnow() + timedelta(seconds=1)
            job.published_at = None

    assert await publish_pending(factory, publication_race) == 1
    async with factory() as db:
        job = await db.get(CheckJob, identifiers[0])
        assert job.published_at is None and job.retry_at is not None
