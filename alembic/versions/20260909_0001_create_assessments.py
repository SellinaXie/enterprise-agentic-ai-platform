"""Create the V2 assessments application-state table.

Revision ID: 20260909_0001
Revises:
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260909_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persisted assessment state and lifecycle indexes."""
    op.create_table(
        "assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("industry", sa.String(length=120), nullable=False),
        sa.Column("business_problem", sa.Text(), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name=op.f("ck_assessments_assessment_status_values"),
        ),
        sa.CheckConstraint(
            "status != 'completed' OR (result_payload IS NOT NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_assessments_completed_has_result_and_timestamp"),
        ),
        sa.CheckConstraint(
            "status != 'failed' OR "
            "(result_payload IS NULL AND error_code IS NOT NULL AND error_message IS NOT NULL)",
            name=op.f("ck_assessments_failed_has_error_without_result"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assessments"),
    )
    op.create_index("ix_assessments_created_at", "assessments", ["created_at"])
    op.create_index("ix_assessments_status", "assessments", ["status"])


def downgrade() -> None:
    """Remove the V2 assessment state schema."""
    op.drop_index("ix_assessments_status", table_name="assessments")
    op.drop_index("ix_assessments_created_at", table_name="assessments")
    op.drop_table("assessments")
