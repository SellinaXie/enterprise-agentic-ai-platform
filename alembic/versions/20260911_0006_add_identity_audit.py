"""Add authenticated identity audit fields.

Revision ID: 20260911_0006
Revises: 20260910_0005
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260911_0006"
down_revision: str | None = "20260910_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable identity fields so existing V7C records remain valid."""
    op.add_column(
        "assessments", sa.Column("created_by_subject", sa.String(length=255), nullable=True)
    )
    op.create_index(
        "ix_assessments_created_by_subject",
        "assessments",
        ["created_by_subject"],
    )
    op.add_column(
        "human_review_events", sa.Column("reviewer_subject", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "human_review_events", sa.Column("reviewer_email", sa.String(length=320), nullable=True)
    )
    op.add_column(
        "human_review_events", sa.Column("reviewer_role", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "human_review_events", sa.Column("reviewer_issuer", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "human_review_events", sa.Column("request_id", sa.String(length=128), nullable=True)
    )


def downgrade() -> None:
    """Restore the V7C schema without deleting review rows."""
    op.drop_column("human_review_events", "request_id")
    op.drop_column("human_review_events", "reviewer_issuer")
    op.drop_column("human_review_events", "reviewer_role")
    op.drop_column("human_review_events", "reviewer_email")
    op.drop_column("human_review_events", "reviewer_subject")
    op.drop_index("ix_assessments_created_by_subject", table_name="assessments")
    op.drop_column("assessments", "created_by_subject")
