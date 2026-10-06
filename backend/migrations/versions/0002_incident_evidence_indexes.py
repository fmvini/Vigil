"""Evidence lookup indexes corroborated by disposable PG17 retention plans.

Ordinary transactional CREATE INDEX blocks concurrent table writes while building;
deployment must allow that lock. Two indexes add storage and write maintenance.
This migration changes no evidence FK, nullability, retention rule or uniqueness.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_incident_evidence_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_incidents_opening_check_id",
        "incidents",
        ["opening_check_id"],
        postgresql_where=sa.text("opening_check_id IS NOT NULL"),
    )
    op.create_index(
        "ix_incidents_closing_check_id",
        "incidents",
        ["closing_check_id"],
        postgresql_where=sa.text("closing_check_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_incidents_closing_check_id", table_name="incidents")
    op.drop_index("ix_incidents_opening_check_id", table_name="incidents")
