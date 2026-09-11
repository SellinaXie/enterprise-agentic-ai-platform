"""Add V7C runtime gate checkpoints and human review audit history.

Revision ID: 20260910_0005
Revises: 20260910_0004
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260910_0005"
down_revision: str | None = "20260910_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add durable post-synthesis checkpoints and append-only review records."""
    op.drop_constraint(
        "ck_assessments_assessment_status_values",
        "assessments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_assessments_assessment_status_values",
        "assessments",
        "status IN ('pending', 'processing', 'completed', 'failed', 'pending_review')",
    )
    op.create_table(
        "assessment_runtime_states",
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gate_decision", sa.String(length=40), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("candidate_execution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("telemetry", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision_count", sa.Integer(), nullable=False),
        sa.Column("max_revisions", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "gate_decision IN ('auto_complete', 'complete_with_warning', "
            "'require_human_review', 'block_and_escalate')",
            name=op.f("ck_assessment_runtime_states_gate_decision_values"),
        ),
        sa.CheckConstraint(
            "review_status IN ('not_required', 'pending', 'approved', 'rejected', "
            "'revision_requested')",
            name=op.f("ck_assessment_runtime_states_review_status_values"),
        ),
        sa.CheckConstraint(
            "revision_count >= 0 AND max_revisions >= 0 AND revision_count <= max_revisions",
            name=op.f("ck_assessment_runtime_states_revision_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_assessment_runtime_states_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("assessment_id", name=op.f("pk_assessment_runtime_states")),
    )
    op.create_index(
        "ix_assessment_runtime_states_review_status",
        "assessment_runtime_states",
        ["review_status"],
    )
    op.create_table(
        "human_review_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=False),
        sa.Column("new_status", sa.String(length=30), nullable=False),
        sa.Column("reviewer_id", sa.String(length=100), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('requested', 'approved', 'rejected', 'revision_requested', "
            "'revision_submitted')",
            name=op.f("ck_human_review_events_action_values"),
        ),
        sa.CheckConstraint(
            "revision_number >= 0",
            name=op.f("ck_human_review_events_revision_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_human_review_events_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_review_events")),
    )
    op.create_index(
        "ix_human_review_events_assessment_created",
        "human_review_events",
        ["assessment_id", "created_at"],
    )


def downgrade() -> None:
    """Remove V7C state and restore the pre-review assessment status vocabulary."""
    op.drop_index("ix_human_review_events_assessment_created", table_name="human_review_events")
    op.drop_table("human_review_events")
    op.drop_index(
        "ix_assessment_runtime_states_review_status",
        table_name="assessment_runtime_states",
    )
    op.drop_table("assessment_runtime_states")
    op.drop_constraint(
        "ck_assessments_assessment_status_values",
        "assessments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_assessments_assessment_status_values",
        "assessments",
        "status IN ('pending', 'processing', 'completed', 'failed')",
    )
