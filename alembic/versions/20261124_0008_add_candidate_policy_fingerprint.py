"""Record the policy fingerprint each candidate was gated under.

Revision ID: 20261124_0008
Revises: 20261124_0007
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261124_0008"
down_revision: str | None = "20261124_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nullable so versions written before this revision stay valid."""
    op.add_column(
        "assessment_candidate_versions",
        sa.Column("policy_fingerprint", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    """Drop only the fingerprint column; versions remain."""
    op.drop_column("assessment_candidate_versions", "policy_fingerprint")
