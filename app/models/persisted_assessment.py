"""Domain representation of persisted assessment state."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.models.assessment import AssessmentStatus


@dataclass(frozen=True, slots=True)
class PersistedAssessment:
    """Persistence-neutral assessment record used by the service layer."""

    assessment_id: UUID
    status: AssessmentStatus
    request_payload: dict[str, Any]
    result_payload: dict[str, Any] | None
    execution_metadata: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    created_by_subject: str | None = None
