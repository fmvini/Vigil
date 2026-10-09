"""Legal audit integrity, transaction ownership and additive migration coverage."""

from datetime import timedelta
from io import StringIO
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, delete, func, insert, inspect, select, text
from sqlalchemy.exc import DBAPIError
from test_db_postgresql import NOW, incident_values, job_values, rejects, result_values, seed
from test_db_postgresql import pg_engine as pg_engine
from test_db_schema import migration_config

from app.db.base import Base
from app.db.models import CheckJob, CheckResult, Incident, LegalAcceptance, Session, User
from app.db.session import create_engine, create_session_factory

REVISION = "0003_legal_acceptances"
PREVIOUS = "0002_incident_evidence_indexes"
EXISTING_TABLES = (
    "users",
    "sessions",
    "projects",
    "monitors",
    "check_jobs",
    "check_results",
    "incidents",
)
INVALID = [
    {"terms_version": ""},
    {"terms_version": "   "},
    {"terms_version": None},
    {"terms_version": "t" * 33},
    {"privacy_version": ""},
    {"privacy_version": "   "},
    {"privacy_version": None},
    {"privacy_version": "p" * 33},
    {"action": "logout"},
    {"action": "LOGIN"},
    {"action": None},
    {"accepted_at": None},
    {"user_id": None},
    {"user_id": uuid4()},
]


def acceptance(owner_id, **overrides):
    values = dict(
        user_id=owner_id,
        terms_version="2026-10-09",
        privacy_version="2026-10-09",
        accepted_at=NOW,
        action="login",
    )
    return values | overrides


def migrate_to(connection, direction, revision):
    config = migration_config()
    config.attributes["connection"] = connection
    getattr(command, direction)(config, revision)


async def snapshot(connection):
    return {
        name: (await connection.execute(text(f"SELECT * FROM {name} ORDER BY id"))).all()
        for name in EXISTING_TABLES
    }


def test_legal_schema_exact_contract():
    table = LegalAcceptance.__table__
    assert set(table.c.keys()) == {
        "id",
        "user_id",
        "terms_version",
        "privacy_version",
        "accepted_at",
        "action",
    }
    assert all(not column.nullable for column in table.c)
    assert table.c.terms_version.type.length == table.c.privacy_version.type.length == 32
    assert table.c.action.type.length == 16
    assert table.c.accepted_at.type.timezone is True
    assert table.c.accepted_at.default is table.c.accepted_at.server_default is None
    (fk,) = table.c.user_id.foreign_keys
    assert fk.target_fullname == "users.id" and fk.ondelete is None
    (index,) = table.indexes
    assert index.name == "ix_legal_acceptances_user_accepted_at"
    assert list(index.columns.keys()) == ["user_id", "accepted_at"]
    assert not index.unique
    assert {c.name for c in table.constraints if isinstance(c, CheckConstraint)} == {
        "ck_legal_acceptances_terms_version_nonempty",
        "ck_legal_acceptances_privacy_version_nonempty",
        "ck_legal_acceptances_action_values",
    }


def test_legal_migration_offline_is_additive_and_downgrade_scoped():
    output = StringIO()
    command.upgrade(migration_config(output=output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE legal_acceptances" in sql
    assert "accepted_at TIMESTAMP WITH TIME ZONE NOT NULL" in sql
    assert "terms_version VARCHAR(32) NOT NULL" in sql
    assert "privacy_version VARCHAR(32) NOT NULL" in sql
    assert "action VARCHAR(16) NOT NULL" in sql
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in sql
    assert "ON DELETE CASCADE" not in sql
    assert "CREATE INDEX ix_legal_acceptances_user_accepted_at" in sql
    assert "(user_id, accepted_at)" in sql
    assert "INSERT INTO legal_acceptances" not in sql
    for name in EXISTING_TABLES:
        assert f"ALTER TABLE {name}" not in sql
        assert f"UPDATE {name} " not in sql
        assert f"DELETE FROM {name}" not in sql
    output = StringIO()
    command.downgrade(migration_config(output=output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()
    assert "DROP INDEX ix_legal_acceptances_user_accepted_at" in sql
    assert "DROP TABLE legal_acceptances" in sql
    assert "DROP TABLE users" not in sql


@pytest_asyncio.fixture
async def sqlite_legal():
    engine = create_engine("sqlite+aiosqlite:///:memory:", allow_sqlite_for_tests=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.parametrize("invalid", INVALID)
async def test_sqlite_rejects_invalid_acceptance(sqlite_legal, invalid):
    async with sqlite_legal.begin() as connection:
        user_id, _, _ = await seed(connection)
        await rejects(connection, insert(LegalAcceptance).values(**acceptance(user_id, **invalid)))
        assert await connection.scalar(select(func.count()).select_from(LegalAcceptance)) == 0


async def test_orm_uuid_repeated_logins_and_timestamp_required(sqlite_legal):
    factory = create_session_factory(sqlite_legal)
    async with factory.begin() as db:
        user = User(email="legal@example.test", password_hash="synthetic")
        db.add(user)
        await db.flush()
        rows = [
            LegalAcceptance(**acceptance(user.id, action=action))
            for action in ("register", "login", "login")
        ]
        db.add_all(rows)
        await db.flush()
        assert len({row.id for row in rows}) == 3
        assert all(isinstance(row.id, UUID) for row in rows)
    async with sqlite_legal.begin() as connection:
        stored = (await connection.execute(select(LegalAcceptance.__table__))).all()
        assert len(stored) == 3
        # Even raw/Core inserts cannot omit the backend-supplied timestamp.
        values = acceptance(user.id)
        del values["accepted_at"]
        await rejects(connection, insert(LegalAcceptance).values(**values))
        assert (await connection.execute(select(LegalAcceptance.__table__))).all() == stored


async def assert_transaction_rollback(engine):
    factory = create_session_factory(engine)
    # Registration failure rolls back the new user and its acceptance together.
    with pytest.raises(RuntimeError, match="abort registration"):
        async with factory.begin() as db:
            user = User(email="rollback@example.test", password_hash="synthetic")
            db.add(user)
            await db.flush()
            db.add(LegalAcceptance(**acceptance(user.id, action="register")))
            await db.flush()
            raise RuntimeError("abort registration")
    async with factory() as db:
        assert await db.get(User, user.id) is None
        assert (
            await db.scalar(
                select(func.count())
                .select_from(LegalAcceptance)
                .where(LegalAcceptance.user_id == user.id)
            )
            == 0
        )
    # A failed login transaction preserves the existing user and previous audit.
    async with factory.begin() as db:
        user = User(email="existing-legal@example.test", password_hash="synthetic")
        db.add(user)
        await db.flush()
        prior = LegalAcceptance(**acceptance(user.id, action="register"))
        db.add(prior)
    with pytest.raises(RuntimeError, match="abort login"):
        async with factory.begin() as db:
            db.add(LegalAcceptance(**acceptance(user.id)))
            db.add(
                Session(
                    user_id=user.id,
                    token_hash="legal-rollback",
                    csrf_token="synthetic",
                    created_at=NOW,
                    last_seen_at=NOW,
                    expires_at=NOW + timedelta(days=1),
                )
            )
            await db.flush()
            raise RuntimeError("abort login")
    async with factory() as db:
        assert await db.get(User, user.id) is not None
        assert (
            await db.scalars(select(LegalAcceptance.id).where(LegalAcceptance.user_id == user.id))
        ).all() == [prior.id]
        assert (
            await db.scalar(
                select(func.count()).select_from(Session).where(Session.user_id == user.id)
            )
            == 0
        )


async def test_sqlite_registration_and_login_audit_transaction_rollback(sqlite_legal):
    await assert_transaction_rollback(sqlite_legal)


@pytest.mark.postgres
async def test_pg_upgrade_preserves_all_existing_rows_and_catalog(pg_engine):
    async with pg_engine.begin() as connection:
        await connection.run_sync(migrate_to, "downgrade", PREVIOUS)
        user, _, monitor = await seed(connection)
        await connection.execute(
            insert(Session).values(
                user_id=user,
                token_hash="existing-token",
                csrf_token="synthetic",
                created_at=NOW,
                last_seen_at=NOW,
                expires_at=NOW + timedelta(days=1),
            )
        )
        job = job_values(monitor, status="completed", finished_at=NOW + timedelta(seconds=1))
        await connection.execute(insert(CheckJob).values(**job))
        result = result_values(job)
        await connection.execute(insert(CheckResult).values(**result))
        await connection.execute(
            insert(Incident).values(**incident_values(monitor, opening_check_id=result["id"]))
        )
        before = await snapshot(connection)
        assert all(before.values())
        await connection.run_sync(migrate_to, "upgrade", REVISION)
        assert await snapshot(connection) == before
        assert await connection.scalar(select(func.count()).select_from(LegalAcceptance)) == 0
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
        differences = await connection.run_sync(
            lambda c: compare_metadata(
                MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata
            )
        )
        assert differences == []
        columns = await connection.run_sync(lambda c: inspect(c).get_columns("legal_acceptances"))
        assert next(c for c in columns if c["name"] == "accepted_at")["type"].timezone
        for action in ("register", "login", "login"):
            await connection.execute(
                insert(LegalAcceptance).values(**acceptance(user, action=action))
            )
        assert await connection.scalar(select(func.count()).select_from(LegalAcceptance)) == 3
        for invalid in INVALID:
            statement = insert(LegalAcceptance).values(**acceptance(user, **invalid))
            if any(isinstance(value, str) and len(value) > 32 for value in invalid.values()):
                # PostgreSQL VARCHAR length enforcement has SQLSTATE 22001,
                # outside asyncpg's IntegrityError mapping for CHECK/NOT NULL/FK.
                with pytest.raises(DBAPIError) as error:
                    async with connection.begin_nested():
                        await connection.execute(statement)
                assert error.value.orig.sqlstate == "22001"
            else:
                await rejects(connection, statement)
        await connection.execute(
            insert(LegalAcceptance).values(
                **acceptance(user, terms_version="t" * 32, privacy_version="p" * 32)
            )
        )
        values = acceptance(user)
        del values["accepted_at"]
        await rejects(connection, insert(LegalAcceptance).values(**values))
        assert await snapshot(connection) == before
        await connection.run_sync(migrate_to, "downgrade", PREVIOUS)
        assert await snapshot(connection) == before
        assert "legal_acceptances" not in await connection.run_sync(
            lambda c: inspect(c).get_table_names()
        )
        await connection.run_sync(migrate_to, "upgrade", REVISION)
        assert await snapshot(connection) == before


@pytest.mark.postgres
async def test_pg_user_fk_never_cascades_and_owned_cleanup_preserves_other_audit(pg_engine):
    async with pg_engine.begin() as connection:
        users = [uuid4(), uuid4()]
        for number, user in enumerate(users):
            await connection.execute(
                insert(User).values(
                    id=user, email=f"legal-{number}@example.test", password_hash="synthetic"
                )
            )
            await connection.execute(insert(LegalAcceptance).values(**acceptance(user)))
        await rejects(connection, delete(User).where(User.id == users[0]))
        await connection.execute(delete(LegalAcceptance).where(LegalAcceptance.user_id == users[0]))
        await connection.execute(delete(User).where(User.id == users[0]))
        assert (await connection.scalars(select(User.id))).all() == [users[1]]
        assert (await connection.scalars(select(LegalAcceptance.user_id))).all() == [users[1]]


@pytest.mark.postgres
async def test_pg_registration_and_login_audit_transaction_rollback(pg_engine):
    await assert_transaction_rollback(pg_engine)


@pytest.mark.postgres
async def test_pg_migration_ddl_and_revision_rollback(pg_engine):
    async with pg_engine.begin() as connection:
        await connection.run_sync(migrate_to, "downgrade", PREVIOUS)
        await seed(connection)
        before = await snapshot(connection)
    async with pg_engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(migrate_to, "upgrade", REVISION)
        assert "legal_acceptances" in await connection.run_sync(
            lambda c: inspect(c).get_table_names()
        )
        await transaction.rollback()
    async with pg_engine.begin() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == PREVIOUS
        assert "legal_acceptances" not in await connection.run_sync(
            lambda c: inspect(c).get_table_names()
        )
        assert await snapshot(connection) == before
