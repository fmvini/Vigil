"""Append-only legal acceptance history for successful register/login operations.

No historical acceptances are inferred for existing users. Authentication services
provide the timestamp and append in their transaction. The FK does not cascade
user deletions; no version uniqueness can overwrite or deduplicate login history.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_legal_acceptances"
down_revision = "0002_incident_evidence_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "legal_acceptances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("terms_version", sa.String(length=32), nullable=False),
        sa.Column("privacy_version", sa.String(length=32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_legal_acceptances")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_legal_acceptances_user_id_users")
        ),
        sa.CheckConstraint(
            "length(trim(terms_version)) > 0 AND length(terms_version) <= 32",
            name=op.f("ck_legal_acceptances_terms_version_nonempty"),
        ),
        sa.CheckConstraint(
            "length(trim(privacy_version)) > 0 AND length(privacy_version) <= 32",
            name=op.f("ck_legal_acceptances_privacy_version_nonempty"),
        ),
        sa.CheckConstraint(
            "action IN ('register', 'login')",
            name=op.f("ck_legal_acceptances_action_values"),
        ),
    )
    op.create_index(
        "ix_legal_acceptances_user_accepted_at", "legal_acceptances", ["user_id", "accepted_at"]
    )


def downgrade():
    op.drop_index("ix_legal_acceptances_user_accepted_at", table_name="legal_acceptances")
    op.drop_table("legal_acceptances")
