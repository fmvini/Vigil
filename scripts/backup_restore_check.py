"""Opt-in backup drill for the local PG17 Compose cluster, without runtime writes.

Run using backend/.venv Python and explicit VIGIL_BACKUP_DATABASE_URL.
Artifacts contain private data and stay under .cache/backup-restore/.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import asyncpg

TABLES = (
    "alembic_version",
    "check_jobs",
    "check_results",
    "incidents",
    "legal_acceptances",
    "monitors",
    "projects",
    "sessions",
    "users",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPTIONS = "-c statement_timeout=30000 -c lock_timeout=5000 -c max_parallel_workers_per_gather=0"


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    user: str
    password: str = field(repr=False)
    database: str = "vigil"

    def connection(self, database=None):
        return dict(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=database or self.database,
            timeout=10,
            command_timeout=30,
            server_settings={
                "timezone": "UTC",
                "datestyle": "ISO, YMD",
                "extra_float_digits": "3",
                "max_parallel_workers_per_gather": "0",
            },
        )


def parse_target(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"postgresql", "postgresql+asyncpg"}
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port != 55433
        or parsed.path != "/vigil"
        or parsed.query
        or parsed.fragment
        or not parsed.username
        or not parsed.password
    ):
        raise ValueError("Use explicit local PG17 Compose URL on 55433/database vigil")
    return Target(parsed.hostname, parsed.port, unquote(parsed.username), unquote(parsed.password))


def identifier(value):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
        raise ValueError("Invalid SQL identifier")
    return '"' + value + '"'


def assert_owned_restore(name, source):
    if name == source or not re.fullmatch(r"vigil_restore_qa_[a-f0-9]{32}", name):
        raise ValueError("Cleanup requires the exclusive restore database of this run")


class CommandFailed(RuntimeError):
    pass


class CommandTimedOut(RuntimeError):
    pass


async def command(*arguments, timeout=60):
    process = await asyncio.create_subprocess_exec(
        *map(str, arguments), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout)
    except BaseException as error:
        if process.returncode is None:
            process.kill()  # Only this command's client; server-side work may remain.
            await asyncio.wait_for(process.wait(), 5)
        if isinstance(error, (TimeoutError, asyncio.CancelledError)):
            raise CommandTimedOut("Own client timed out; inspect server before retry") from None
        raise
    if process.returncode:
        # Native stderr can contain private rows/connection information.
        raise CommandFailed("Native command failed; private stderr is not published")
    return stdout.decode("utf-8").strip()


async def table_digest(db, schema, table, key):
    if not db.is_in_transaction():
        raise ValueError("Fingerprint requires a caller-owned consistent transaction")
    digest, count = hashlib.sha256(), 0
    query = (
        f"SELECT row_to_json(r)::text FROM {identifier(schema)}.{identifier(table)} r "
        f"ORDER BY {identifier(key)}"
    )
    async for row in db.cursor(query, prefetch=100):
        encoded = row[0].encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


async def manifest(db):
    names = tuple(
        await db.fetchval(
            "SELECT array_agg(tablename ORDER BY tablename) FROM pg_tables WHERE schemaname='public'"
        )
        or ()
    )
    if names != TABLES:
        raise ValueError("Public schema differs from the known Vigil tables; review tooling")
    revision = await db.fetch("SELECT version_num FROM public.alembic_version")
    if len(revision) != 1:
        raise ValueError("Expected one Alembic head")
    result = {"revision": revision[0][0], "tables": {}}
    for table in TABLES:
        columns = await db.fetch(
            "SELECT column_name, data_type, udt_name, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema='public' AND table_name=$1 "
            "ORDER BY ordinal_position",
            table,
        )
        constraints = await db.fetch(
            "SELECT conname, contype::text, pg_get_constraintdef(oid, true) AS definition, convalidated "
            "FROM pg_constraint WHERE conrelid=$1::regclass ORDER BY conname",
            "public." + table,
        )
        indexes = await db.fetch(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' "
            "AND tablename=$1 ORDER BY indexname",
            table,
        )
        result["tables"][table] = {
            **await table_digest(
                db, "public", table, "version_num" if table == "alembic_version" else "id"
            ),
            "columns": [dict(row) for row in columns],
            "constraints": [dict(row) for row in constraints],
            "indexes": [dict(row) for row in indexes],
        }
    return result


def compare_manifests(source, restored):
    if source != restored:
        raise ValueError("Restored rows or schema differ from the exported source snapshot")


async def drill(target, container):
    run_id = uuid4().hex
    restore_name = "vigil_restore_qa_" + run_id
    assert_owned_restore(restore_name, target.database)
    directory = PROJECT_ROOT / ".cache" / "backup-restore" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    dump_path, report_path = directory / "public.dump", directory / "report.json"
    remote_dump = "/tmp/" + restore_name + ".dump"
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "result": "failed",
        "restore_database": restore_name,
        "cleanup": "not_created",
        "scope": "public",
        "external_checks_executed": False,
        "dump_path": str(dump_path),
    }
    created = timed_out = container_verified = False
    source = restored = None
    started = time.monotonic()

    async def postgres(*args, timeout=60):
        return await command(
            "docker", "exec", "-e", "PGOPTIONS=" + OPTIONS, container, *args, timeout=timeout
        )

    try:
        report["stage"] = "inspect_container"
        info = json.loads(await command("docker", "inspect", container))[0]
        labels = info["Config"].get("Labels") or {}
        environment = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
        if (
            labels.get("com.docker.compose.project") != "vigil"
            or labels.get("com.docker.compose.service") != "postgres"
            or environment.get("POSTGRES_USER") != target.user
            or environment.get("POSTGRES_DB") != target.database
        ):
            raise ValueError("Container does not match the local Vigil Compose PostgreSQL target")
        report["stage"] = "validate_cluster"
        source = await asyncpg.connect(**target.connection())
        version = int(await source.fetchval("SHOW server_version_num"))
        if not 170000 <= version < 180000:
            raise ValueError("This drill requires PostgreSQL 17")
        identity = str(await source.fetchval("SELECT system_identifier FROM pg_control_system()"))
        container_identity = await postgres(
            "psql",
            "-X",
            "-w",
            "-U",
            target.user,
            "-d",
            target.database,
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "SELECT system_identifier FROM pg_control_system()",
        )
        if identity != container_identity:
            raise ValueError("Network connection and container point to different clusters")
        container_verified = True
        report["server_version_num"] = version
        report["stage"] = "snapshot_and_dump"
        async with source.transaction(isolation="repeatable_read", readonly=True):
            snapshot = await source.fetchval("SELECT pg_export_snapshot()")
            expected = await manifest(source)
            report["source"] = expected
            await postgres(
                "pg_dump",
                "-w",
                "-U",
                target.user,
                "-d",
                target.database,
                "-Fc",
                "--schema=public",
                "--strict-names",
                "--snapshot=" + snapshot,
                "--file=" + remote_dump,
            )
        report["stage"] = "copy_dump"
        await command("docker", "cp", container + ":" + remote_dump, dump_path)
        with dump_path.open("rb") as dumped:
            report["dump_sha256"] = hashlib.file_digest(dumped, "sha256").hexdigest()
        report["dump_bytes"] = dump_path.stat().st_size
        report["stage"] = "create_restore_database"
        await postgres("createdb", "-w", "-U", target.user, "--template=template0", restore_name)
        created = True
        report["cleanup"] = "pending"
        report["stage"] = "restore_dump"
        await postgres(
            "pg_restore",
            "-w",
            "-U",
            target.user,
            "-d",
            restore_name,
            "--single-transaction",
            "--clean",
            "--if-exists",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            remote_dump,
        )
        report["stage"] = "verify_content"
        restored = await asyncpg.connect(**target.connection(restore_name))
        async with restored.transaction(isolation="repeatable_read", readonly=True):
            actual = await manifest(restored)
        report["restored"] = actual
        compare_manifests(expected, actual)
        report["content_verified"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
        timed_out = isinstance(error, CommandTimedOut)
        if timed_out:
            report["cleanup"] = "pending_review"
    finally:
        for connection in (restored, source):
            if connection is not None:
                try:
                    await connection.close(timeout=5)
                except Exception as error:
                    timed_out = True
                    report["cleanup"] = "pending_review"
                    report["connection_cleanup_error_type"] = type(error).__name__
        if created and not timed_out:
            try:
                assert_owned_restore(restore_name, target.database)
                await postgres("dropdb", "-w", "-U", target.user, restore_name, timeout=15)
                check = await asyncpg.connect(**target.connection())
                try:
                    if await check.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)", restore_name
                    ):
                        raise ValueError("Restore database still exists after cleanup")
                finally:
                    await check.close(timeout=5)
                report["cleanup"] = "confirmed"
            except Exception as error:
                report["cleanup"] = "pending_review"
                report["cleanup_error_type"] = type(error).__name__
        if container_verified and report["cleanup"] != "pending_review":
            try:
                await command(
                    "docker", "exec", container, "rm", "-f", "--", remote_dump, timeout=15
                )
            except Exception as error:
                report["temporary_dump_cleanup_error_type"] = type(error).__name__
        report["result"] = (
            "passed"
            if report.get("content_verified")
            and report["cleanup"] == "confirmed"
            and not report.get("temporary_dump_cleanup_error_type")
            else "failed"
        )
        report["duration_seconds"] = round(time.monotonic() - started, 3)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return report, report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="vigil-postgres-1")
    args = parser.parse_args(argv)
    try:
        target = parse_target(os.environ.get("VIGIL_BACKUP_DATABASE_URL", ""))
        report, path = asyncio.run(drill(target, args.container))
    except Exception as error:
        print(f"Backup drill rejected: {type(error).__name__}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "result": report["result"],
                "cleanup": report["cleanup"],
                "report": str(path),
                "duration_seconds": report["duration_seconds"],
            }
        )
    )
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
