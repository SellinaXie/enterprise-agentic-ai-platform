"""Service/API compatibility and execution-mode precedence tests for V5."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.models import (
    AgentTerminationReason,
    AssessmentExecutionMetadata,
    DeterministicExecutionMetadata,
)
from app.agents.multi_agent_models import (
    MultiAgentDurations,
    MultiAgentErrors,
    MultiAgentExecutionMetadata,
    MultiAgentStatus,
    MultiAgentStatuses,
    MultiAgentTerminationReason,
)
from app.api.dependencies import (
    get_agentic_assessment_workflow,
    get_multi_agent_assessment_workflow,
)
from app.core.config import Settings
from app.core.exceptions import AssessmentGenerationError
from app.db.models.assessment import AssessmentModel
from app.models.assessment import AssessmentStatus, ExternalEvidenceStatus
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.repositories.assessments import AssessmentRepository
from app.schemas.assessment import AssessmentRequest, AssessmentResponse, SourceReference
from app.services.assessments import AssessmentGenerator, AssessmentService
from tests.factories import build_assessment_result


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Manual compliance review is slow",
        desired_outcome="Reduce preparation time with human approval",
    )


def _multi_execution() -> MultiAgentExecutionMetadata:
    return MultiAgentExecutionMetadata(
        agent_statuses=MultiAgentStatuses(
            evidence=MultiAgentStatus.COMPLETED,
            architecture=MultiAgentStatus.COMPLETED,
            risk_governance=MultiAgentStatus.COMPLETED,
            synthesis=MultiAgentStatus.COMPLETED,
        ),
        agent_durations_ms=MultiAgentDurations(
            evidence=1,
            architecture=1,
            risk_governance=1,
            synthesis=1,
        ),
        agent_errors=MultiAgentErrors(),
        tools_used=[],
        tool_calls=0,
        degraded_mode=False,
        degradation_reasons=[],
        termination_reason=MultiAgentTerminationReason.COMPLETED,
        trace=[],
    )


def test_v3_v4_v5_execution_precedence_is_explicit(db_session: Session) -> None:
    generator = Mock()
    generator.generate.return_value = build_assessment_result()

    deterministic = AssessmentService(
        cast(AssessmentGenerator, generator),
        AssessmentRepository(db_session),
    ).generate_assessment(_request())
    assert deterministic.execution == DeterministicExecutionMetadata()

    single_workflow = Mock()
    single_workflow.run.return_value = SimpleNamespace(
        result=build_assessment_result(),
        evidence=(),
        execution=AssessmentExecutionMetadata(
            steps_used=1,
            tools_used=[],
            termination_reason=AgentTerminationReason.AGENT_STOPPED,
            trace=[],
        ),
    )
    single = AssessmentService(
        cast(AssessmentGenerator, generator),
        AssessmentRepository(db_session),
        agentic_workflow=single_workflow,
    ).generate_assessment(_request())
    assert single.execution is not None
    assert single.execution.execution_mode == "single_agent"

    multi_workflow = Mock()
    multi_workflow.run.return_value = SimpleNamespace(
        result=build_assessment_result(),
        evidence=(),
        execution=_multi_execution(),
    )
    multi = AssessmentService(
        cast(AssessmentGenerator, generator),
        AssessmentRepository(db_session),
        agentic_workflow=single_workflow,
        multi_agent_workflow=multi_workflow,
    ).generate_assessment(_request())
    assert multi.execution is not None
    assert multi.execution.execution_mode == "multi_agent"
    multi_workflow.run.assert_called_once()
    assert single_workflow.run.call_count == 1


def test_historical_v4_agentic_metadata_remains_readable() -> None:
    parsed = AssessmentService._parse_execution_metadata(
        {
            "execution_mode": "agentic",
            "steps_used": 1,
            "tools_used": [],
            "termination_reason": "agent_stopped",
            "trace": [],
        }
    )

    assert isinstance(parsed, AssessmentExecutionMetadata)
    assert parsed.execution_mode == "agentic"


def test_multi_agent_flag_suppresses_v4_graph_construction() -> None:
    settings = Settings(
        _env_file=None,
        AGENTIC_WORKFLOW_ENABLED=True,
        MULTI_AGENT_WORKFLOW_ENABLED=True,
    )

    workflow = get_agentic_assessment_workflow(
        agent=Mock(),
        tools=Mock(),
        settings=settings,
    )

    assert workflow is None


def test_multi_agent_service_persists_metadata_and_sanitizes_invented_citations(
    db_session: Session,
) -> None:
    evidence = RetrievedEvidence(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Synthetic approval policy",
        content="Authorized staff retain final approval.",
        similarity_score=0.95,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )
    invented = SourceReference(
        document_id=uuid4(),
        chunk_id=uuid4(),
        document_title="Invented source",
    )
    observed = SourceReference(
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
        document_title=evidence.document_title,
    )
    workflow = Mock()
    workflow.run.return_value = SimpleNamespace(
        result=build_assessment_result().model_copy(
            update={
                "external_evidence_status": ExternalEvidenceStatus.RETRIEVED,
                "source_references": [observed, invented],
            }
        ),
        evidence=(evidence,),
        execution=_multi_execution(),
    )
    repository = AssessmentRepository(db_session)
    service = AssessmentService(
        cast(AssessmentGenerator, Mock()),
        repository,
        multi_agent_workflow=workflow,
    )

    response = service.generate_assessment(_request())
    persisted = repository.get_by_id(response.assessment_id)

    assert response.result is not None
    assert response.result.source_references == [observed]
    assert response.execution == _multi_execution()
    assert persisted is not None
    assert persisted.execution_metadata == _multi_execution().model_dump(mode="json")


def test_multi_agent_synthesis_failure_persists_only_safe_failure_state(
    db_session: Session,
) -> None:
    workflow = Mock()
    workflow.run.side_effect = AssessmentGenerationError()
    service = AssessmentService(
        cast(AssessmentGenerator, Mock()),
        AssessmentRepository(db_session),
        multi_agent_workflow=workflow,
    )

    with pytest.raises(AssessmentGenerationError):
        service.generate_assessment(_request())

    persisted = db_session.scalars(select(AssessmentModel)).one()
    assert persisted.status == AssessmentStatus.FAILED
    assert persisted.error_code == "assessment_generation_error"
    assert persisted.error_message == AssessmentGenerationError.public_message
    assert persisted.result_payload is None
    assert persisted.execution_metadata is None


def test_multi_agent_api_post_get_round_trip_uses_mocked_workflow(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    workflow = Mock()
    workflow.run.return_value = SimpleNamespace(
        result=build_assessment_result(),
        evidence=(),
        execution=_multi_execution(),
    )
    app.dependency_overrides[get_multi_agent_assessment_workflow] = lambda: workflow

    created_response = client.post("/api/v1/assessments", json=_request().model_dump(mode="json"))
    assert created_response.status_code == 200
    created = AssessmentResponse.model_validate(created_response.json())

    retrieved_response = client.get(f"/api/v1/assessments/{created.assessment_id}")
    assert retrieved_response.status_code == 200
    retrieved = AssessmentResponse.model_validate(retrieved_response.json())

    assert created.execution is not None
    assert created.execution.execution_mode == "multi_agent"
    assert retrieved == created
    workflow.run.assert_called_once()
    with session_factory() as session:
        persisted = AssessmentRepository(session).get_by_id(created.assessment_id)
    assert persisted is not None
    assert persisted.execution_metadata == _multi_execution().model_dump(mode="json")
