"""Assessment service database-failure normalization tests."""

from typing import cast
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.exceptions import DatabaseUnavailableError, PersistenceError
from app.schemas.assessment import AssessmentRequest
from app.services.assessments import (
    AssessmentGenerator,
    AssessmentRepositoryProtocol,
    AssessmentService,
)


def build_request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Manual review takes too long",
        desired_outcome="Reduce turnaround time",
    )


def test_operational_error_becomes_database_unavailable() -> None:
    repository = Mock()
    repository.create.side_effect = OperationalError(
        "insert assessment",
        {},
        Exception("connection unavailable"),
    )
    service = AssessmentService(
        cast(AssessmentGenerator, Mock()),
        cast(AssessmentRepositoryProtocol, repository),
    )

    with pytest.raises(DatabaseUnavailableError):
        service.generate_assessment(build_request())

    repository.rollback.assert_called_once_with()


def test_integrity_error_becomes_safe_persistence_error() -> None:
    repository = Mock()
    repository.create.side_effect = IntegrityError(
        "insert assessment",
        {},
        Exception("constraint failure"),
    )
    service = AssessmentService(
        cast(AssessmentGenerator, Mock()),
        cast(AssessmentRepositoryProtocol, repository),
    )

    with pytest.raises(PersistenceError):
        service.generate_assessment(build_request())

    repository.rollback.assert_called_once_with()
