"""Offline evidence-FK audit; never connects to a database or changes the schema."""

import json
import re
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.db.models import Incident

EVIDENCE_COLUMNS = ("opening_check_id", "closing_check_id")


def normalized(sql):
    return " ".join(sql.split())


def offline_migration():
    """Render the repository's actual head, using Alembic's SQL-only mode."""
    output = StringIO()
    config = Config(output_buffer=output)
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "migrations")
    )
    # A fixed dummy URL selects the dialect; no environment/runtime DSN is read.
    config.set_main_option(
        "sqlalchemy.url", "postgresql+asyncpg://offline:unused@127.0.0.1/offline"
    )
    head = ScriptDirectory.from_config(config).get_current_head()
    command.upgrade(config, "head", sql=True)
    return head, output.getvalue()


def audit(table, migration_sql, head):
    """Compare evidence semantics and declared incident indexes against offline DDL.

    This deliberately accepts only a CREATE TABLE baseline and additive indexes,
    not arbitrary ALTER/DROP SQL. If later migrations alter incidents, require a live catalog audit
    rather than claiming offline parity from an incomplete SQL parser.
    """
    sql = normalized(migration_sql)
    definitions = re.findall(r"CREATE TABLE incidents \((.*?)\);", sql)
    definition = definitions[0] if len(definitions) == 1 else ""
    unsupported_ddl = bool(re.search(r"\b(?:ALTER|DROP)\b", sql))
    supported = bool(definition) and not unsupported_ddl
    metadata_indexes = {
        normalized(str(CreateIndex(index).compile(dialect=postgresql.dialect())))
        for index in table.indexes
    }
    migration_indexes = set(re.findall(r"CREATE (?:UNIQUE )?INDEX \w+ ON incidents .*?;", sql))
    migration_indexes = {item.removesuffix(";") for item in migration_indexes}
    foreign_keys = {}
    contract_matches = supported
    for name in EVIDENCE_COLUMNS:
        column = table.c[name]
        keys = list(column.foreign_keys)
        key = keys[0] if len(keys) == 1 else None
        metadata_valid = (
            key is not None
            and column.nullable
            and key.target_fullname == "check_results.id"
            and key.ondelete == "SET NULL"
        )
        declarations = re.findall(rf"\b{name} UUID([^,]*)", definition)
        migration_valid = (
            len(declarations) == 1
            and "NOT NULL" not in declarations[0]
            and definition.count(
                f"FOREIGN KEY({name}) REFERENCES check_results (id) ON DELETE SET NULL"
            )
            == 1
        )
        candidates = []
        for index in sorted(table.indexes, key=lambda item: item.name):
            first = list(index.expressions)[0]
            if (
                getattr(first, "name", None) == name
                and getattr(first, "table", None) is table
                and (index.dialect_options["postgresql"].get("using") or "btree") == "btree"
            ):
                predicate = index.dialect_options["postgresql"].get("where")
                candidates.append(
                    {
                        "name": index.name,
                        "predicate": str(predicate) if predicate is not None else None,
                    }
                )
        foreign_keys[name] = {
            "nullable": column.nullable,
            "target": key.target_fullname if key is not None else None,
            "ondelete": key.ondelete if key is not None else None,
            "contract_matches": bool(metadata_valid and migration_valid and supported),
            "declared_btree_leading_candidates": candidates,
        }
        contract_matches = contract_matches and metadata_valid and migration_valid
    indexes_match = supported and metadata_indexes == migration_indexes
    return {
        "protocol_version": 1,
        "scope": "incident_evidence_fks_and_indexes_offline",
        "postgresql_executed": False,
        "migration_head": head,
        "offline_ddl_supported": supported,
        "retention_contract_matches_migration": bool(contract_matches and indexes_match),
        "incident_indexes_match": bool(indexes_match),
        "evidence_foreign_keys": foreign_keys,
        "without_declared_btree_leading_candidate": [
            name
            for name, details in foreign_keys.items()
            if not details["declared_btree_leading_candidates"]
        ],
        "limitations": [
            "Offline DDL/metadata only; no live catalog, migration execution or query plan.",
            "Index candidates do not prove predicate applicability or planner choice.",
            "No measurement of retention cost, locks, SET NULL behavior or improvement.",
            "ALTER/DROP SQL is conservatively rejected; requires a live catalog contract check.",
        ],
    }


def main():
    head, sql = offline_migration()
    report = audit(Incident.__table__, sql, head)
    print(json.dumps(report, allow_nan=False, sort_keys=True))
    return 0 if report["retention_contract_matches_migration"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
