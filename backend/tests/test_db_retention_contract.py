"""Offline drift regressions, not evidence of PostgreSQL retention performance."""

import json

import pytest
from sqlalchemy import Index, MetaData, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.audit_retention_contract import audit, main, normalized, offline_migration
from app.db.base import Base
from app.db.models import Incident


@pytest.fixture(scope="module")
def migration():
    return offline_migration()


def copied_incidents():
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata)
    return metadata.tables["incidents"]


def test_current_evidence_contract_matches_actual_offline_migration(migration):
    head, sql = migration
    report = audit(Incident.__table__, sql, head)
    assert report["retention_contract_matches_migration"]
    assert report["scope"] == "incident_evidence_fks_and_indexes_offline"
    assert report["incident_indexes_match"] and report["offline_ddl_supported"]
    assert not report["postgresql_executed"]
    for details in report["evidence_foreign_keys"].values():
        assert details["contract_matches"]
        assert details["nullable"] and details["ondelete"] == "SET NULL"
        assert details["target"] == "check_results.id"
    json.dumps(report, allow_nan=False)


def test_frozen_initial_revision_has_no_evidence_leading_indexes(migration):
    # This is a factual baseline of the frozen revision, not a requirement to
    # keep current metadata unindexed once an optimization is corroborated.
    _, sql = migration
    if "Running upgrade 0001_initial ->" in sql:
        sql = sql.split("-- Running upgrade 0001_initial ->", 1)[0]
    statements = normalized(sql).split(";")
    indexes = [item.strip() for item in statements if "INDEX " in item and "ON incidents " in item]
    assert indexes
    assert all(
        "opening_check_id" not in item and "closing_check_id" not in item for item in indexes
    )


@pytest.mark.parametrize("name", ["opening_check_id", "closing_check_id"])
@pytest.mark.parametrize("change", ["nullable", "ondelete", "target"])
def test_audit_rejects_evidence_semantic_drift(migration, name, change):
    head, sql = migration
    table = copied_incidents()
    column = table.c[name]
    if change == "nullable":
        column.nullable = False
    elif change == "ondelete":
        next(iter(column.foreign_keys)).ondelete = "CASCADE"
    else:
        sql = sql.replace(
            f"FOREIGN KEY({name}) REFERENCES check_results (id)",
            f"FOREIGN KEY({name}) REFERENCES check_jobs (id)",
        )
    report = audit(table, sql, head)
    assert not report["retention_contract_matches_migration"]
    assert not report["evidence_foreign_keys"][name]["contract_matches"]


def test_audit_detects_metadata_only_index_and_records_candidate_predicate(migration):
    head, sql = migration
    table = copied_incidents()
    index = Index(
        "qa_evidence_index",
        table.c.opening_check_id,
        postgresql_where=text("opening_check_id IS NOT NULL"),
    )
    report = audit(table, sql, head)
    assert (
        not report["retention_contract_matches_migration"] and not report["incident_indexes_match"]
    )
    assert report["evidence_foreign_keys"]["opening_check_id"][
        "declared_btree_leading_candidates"
    ] == [{"name": index.name, "predicate": "opening_check_id IS NOT NULL"}]


@pytest.mark.parametrize("kind", ["nonleading", "hash"])
def test_audit_does_not_report_irrelevant_indexes_as_btree_candidates(migration, kind):
    head, sql = migration
    table = copied_incidents()
    if kind == "nonleading":
        index = Index("qa_nonleading_index", table.c.monitor_id, table.c.opening_check_id)
    else:
        index = Index("qa_hash_index", table.c.opening_check_id, postgresql_using="hash")
    report = audit(table, sql, head)
    candidates = report["evidence_foreign_keys"]["opening_check_id"][
        "declared_btree_leading_candidates"
    ]
    assert all(candidate["name"] != index.name for candidate in candidates)


@pytest.mark.parametrize(
    "ddl",
    [
        "ALTER TABLE incidents ALTER COLUMN opening_check_id SET NOT NULL;",
        "DROP INDEX ix_incidents_ended_at;",
        "DROP TABLE incidents;",
        "ALTER INDEX ix_incidents_ended_at RENAME TO renamed_index;",
    ],
)
def test_audit_refuses_to_claim_parity_for_unsupported_ddl(migration, ddl):
    head, sql = migration
    report = audit(Incident.__table__, sql + ddl, head)
    assert (
        not report["offline_ddl_supported"] and not report["retention_contract_matches_migration"]
    )


def test_cli_remains_offline_with_invalid_runtime_urls(monkeypatch, capsys):
    def forbid_connection(*args, **kwargs):
        pytest.fail("Offline audit attempted a database connection")

    monkeypatch.setattr(Engine, "connect", forbid_connection)
    monkeypatch.setattr(AsyncEngine, "connect", forbid_connection)
    monkeypatch.setenv("VIGIL_DATABASE_URL", "invalid-private-runtime-sentinel")
    monkeypatch.setenv("VIGIL_TEST_DATABASE_URL", "invalid-private-test-sentinel")
    assert main() == 0
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    report = json.loads(captured.out)
    assert report["retention_contract_matches_migration"] and not report["postgresql_executed"]
    assert "private" not in captured.out
