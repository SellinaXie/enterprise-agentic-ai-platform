"""Add compact V4 agent execution metadata.

Revision ID: 20260909_0003
Revises: 20260909_0002
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260909_0003"
down_revision: str | None = "20260909_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add one nullable JSONB field without changing V1-V3 records."""
    op.add_column(
        "assessments",
        sa.Column(
            "execution_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove only the V4 execution metadata field."""
    op.drop_column("assessments", "execution_metadata")
