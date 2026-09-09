"""SQLAlchemy model for persisted assessment lifecycle state."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.assessment import AssessmentStatus

JSON_PAYLOAD = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class AssessmentModel(Base):
    """Persisted request, result, and lifecycle state for one assessment."""

    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(
            "status != 'completed' OR (result_payload IS NOT NULL AND completed_at IS NOT NULL)",
            name="completed_has_result_and_timestamp",
        ),
        CheckConstraint(
            "status != 'failed' OR "
            "(result_payload IS NULL AND error_code IS NOT NULL AND error_message IS NOT NULL)",
            name="failed_has_error_without_result",
        ),
        Index("ix_assessments_status", "status"),
        Index("ix_assessments_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    status: Mapped[AssessmentStatus] = mapped_column(
        Enum(
            AssessmentStatus,
            values_callable=lambda statuses: [status.value for status in statuses],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="assessment_status_values",
            length=20,
        ),
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(120), nullable=False)
    business_problem: Mapped[str] = mapped_column(Text, nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
