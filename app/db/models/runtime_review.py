"""Persistence models for V7C gate checkpoints and append-only review events."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.assessment import JSON_PAYLOAD, utc_now


class AssessmentRuntimeStateModel(Base):
    """One mutable current checkpoint; immutable transitions live in review events."""

    __tablename__ = "assessment_runtime_states"
    __table_args__ = (
        CheckConstraint(
            "gate_decision IN ('auto_complete', 'complete_with_warning', "
            "'require_human_review', 'block_and_escalate')",
            name="gate_decision_values",
        ),
        CheckConstraint(
            "review_status IN ('not_required', 'pending', 'approved', 'rejected', "
            "'revision_requested')",
            name="review_status_values",
        ),
        CheckConstraint(
            "revision_count >= 0 AND max_revisions >= 0 AND revision_count <= max_revisions",
            name="revision_bounds",
        ),
        Index("ix_assessment_runtime_states_review_status", "review_status"),
    )

    assessment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    gate_decision: Mapped[str] = mapped_column(String(40), nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON_PAYLOAD, nullable=False)
    candidate_result: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD, nullable=True)
    candidate_execution: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD, nullable=True)
    telemetry: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_revisions: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.current_timestamp(),
        nullable=False,
    )


class HumanReviewEventModel(Base):
    """Append-only human review audit event."""

    __tablename__ = "human_review_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('requested', 'approved', 'rejected', 'revision_requested', "
            "'revision_submitted')",
            name="action_values",
        ),
        CheckConstraint("revision_number >= 0", name="revision_nonnegative"),
        Index("ix_human_review_events_assessment_created", "assessment_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    assessment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(30), nullable=False)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewer_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    reviewer_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reviewer_issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSON_PAYLOAD, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
