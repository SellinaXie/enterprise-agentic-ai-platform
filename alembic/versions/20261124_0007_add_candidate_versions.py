"""Add append-only assessment candidate versions.

Revision ID: 20261124_0007
Revises: 20260911_0006
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261124_0007"
down_revision: str | None = "20260911_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep every gated candidate so reviewers can compare revisions."""
    op.create_table(
        "assessment_candidate_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("execution_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gate_decision", sa.String(length=40), nullable=False),
        sa.Column("gate_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feedback_review_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version_number >= 0",
            name=op.f("ck_assessment_candidate_versions_version_nonnegative"),
        ),
        sa.CheckConstraint(
            "gate_decision IN ('auto_complete', 'complete_with_warning', "
            "'require_human_review', 'block_and_escalate')",
            name=op.f("ck_assessment_candidate_versions_gate_decision_values"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_assessment_candidate_versions_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_review_id"],
            ["human_review_events.id"],
            # Explicit short name: the convention-derived one exceeds PostgreSQL's 63 bytes.
            name=op.f("fk_candidate_versions_feedback_review_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_candidate_versions")),
        sa.UniqueConstraint(
            "assessment_id",
            "version_number",
            name=op.f("uq_assessment_candidate_versions_assessment_id"),
        ),
    )


def downgrade() -> None:
    """Remove candidate version history; current checkpoints remain intact."""
    op.drop_table("assessment_candidate_versions")
