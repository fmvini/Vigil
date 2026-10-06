"""Read-only database and migration readiness; never applies migrations."""

from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text


def migration_head() -> str:
    # Anchor to the installed backend, independent of the process working directory.
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "migrations"))
    head = scripts.get_current_head()  # Multiple heads are a deployment error.
    if head is None:
        raise ValueError("Migration head is missing")
    return head


async def database_ready(engine, *, expected_head: str | None, sqlite_test_engine=False):
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        # Only an explicitly injected SQLite test engine can bypass Alembic.
        if sqlite_test_engine:
            return
        if expected_head is None:
            raise ValueError("Migration head is unavailable")
        revisions = (
            (await connection.execute(text("SELECT version_num FROM alembic_version LIMIT 2")))
            .scalars()
            .all()
        )
        if revisions != [expected_head]:
            raise ValueError("Database migration revision does not match the application")
