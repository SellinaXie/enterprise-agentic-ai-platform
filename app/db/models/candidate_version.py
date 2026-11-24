"""Append-only persisted candidate versions for human-review version comparison."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.assessment import JSON_PAYLOAD, utc_now


class AssessmentCandidateVersionModel(Base):
    """One gated candidate; version 0 is the original and each revision appends one row."""

    __tablename__ = "assessment_candidate_versions"
    __table_args__ = (
        UniqueConstraint("assessment_id", "version_number"),
        CheckConstraint("version_number >= 0", name="version_nonnegative"),
        CheckConstraint(
            "gate_decision IN ('auto_complete', 'complete_with_warning', "
            "'require_human_review', 'block_and_escalate')",
            name="gate_decision_values",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    assessment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    execution_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD, nullable=True)
    gate_decision: Mapped[str] = mapped_column(String(40), nullable=False)
    gate_result: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    feedback_review_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        # Explicit short name: the convention-derived one exceeds PostgreSQL's 63 bytes.
        ForeignKey(
            "human_review_events.id",
            ondelete="SET NULL",
            name="fk_candidate_versions_feedback_review_id",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
