"""Assessment and API integration tests for the optional V4 graph path."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import OpenAI
from sqlalchemy.orm import Session, sessionmaker

from app.agents.assessment_agent import OpenAIAssessmentAgent
from app.agents.models import AgentDecision, AgentDecisionType, AgentToolRequest
from app.api.dependencies import get_agentic_assessment_workflow
from app.graph.workflow import AgenticAssessmentWorkflow
from app.models.assessment import ExternalEvidenceStatus
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.repositories.assessments import AssessmentRepository
from app.schemas.assessment import AssessmentRequest, AssessmentResponse, SourceReference
from app.services.assessments import AssessmentGenerator, AssessmentService
from app.services.llm import OpenAIAssessmentGenerator
from app.tools.models import SearchKnowledgeArguments, ToolExecutionResult
from app.tools.registry import ToolDefinition, ToolRegistry
from tests.factories import build_assessment_result


class RetrievingAgent:
    """Fake single agent that retrieves once and then produces a cited result."""

    def __init__(self, evidence: RetrievedEvidence) -> None:
        self._evidence = evidence
        self._decisions = 0

    def decide(self, **_: Any) -> AgentDecision:
        self._decisions += 1
        if self._decisions == 1:
            return AgentDecision(
                action=AgentDecisionType.TOOL,
                tool_request=AgentToolRequest(
                    name="search_knowledge",
                    arguments={"query": "human review controls", "top_k": 2},
                ),
            )
        return AgentDecision(action=AgentDecisionType.SYNTHESIZE)

    def synthesize(self, **_: Any):  # noqa: ANN201
        return build_assessment_result().model_copy(
            update={
                "external_evidence_status": ExternalEvidenceStatus.RETRIEVED,
                "source_references": [
                    SourceReference(
                        document_id=self._evidence.document_id,
                        chunk_id=self._evidence.chunk_id,
                        document_title=self._evidence.document_title,
                    )
                ],
            }
        )


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Manual compliance review is slow",
        desired_outcome="Reduce preparation time with human approval",
    )


def _workflow() -> tuple[AgenticAssessmentWorkflow, Mock, RetrievedEvidence]:
    evidence = RetrievedEvidence(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Synthetic human review policy",
        content="Authorized staff retain final approval.",
        similarity_score=0.96,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )
    handler = Mock(
        return_value=ToolExecutionResult(
            tool_name="search_knowledge",
            success=True,
            summary="Knowledge search returned 1 relevant chunk(s).",
            evidence=(evidence,),
        )
    )
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="search_knowledge",
                description="Search existing knowledge.",
                arguments_model=SearchKnowledgeArguments,
                handler=handler,
            )
        ]
    )
    return (
        AgenticAssessmentWorkflow(
            agent=RetrievingAgent(evidence),
            tools=registry,
            max_steps=5,
            max_tool_calls=5,
            recursion_limit=25,
        ),
        handler,
        evidence,
    )


def test_agentic_service_persists_result_citations_and_execution_metadata(
    db_session: Session,
) -> None:
    workflow, handler, evidence = _workflow()
    generator = Mock()
    rag = Mock()
    repository = AssessmentRepository(db_session)
    service = AssessmentService(
        cast(AssessmentGenerator, generator),
        repository,
        rag,
        agentic_workflow=workflow,
    )

    response = service.generate_assessment(_request())
    persisted = repository.get_by_id(response.assessment_id)

    assert response.execution is not None
    assert response.execution.execution_mode == "agentic"
    assert response.execution.steps_used == 2
    assert response.execution.tools_used == ["search_knowledge"]
    assert response.result is not None
    assert response.result.source_references[0].chunk_id == evidence.chunk_id
    assert persisted is not None
    assert persisted.execution_metadata == response.execution.model_dump(mode="json")
    generator.generate.assert_not_called()
    rag.prepare.assert_not_called()
    handler.assert_called_once()


def test_disabled_agentic_path_preserves_deterministic_v3_behavior(db_session: Session) -> None:
    generator = Mock()
    generator.generate.return_value = build_assessment_result()
    service = AssessmentService(
        cast(AssessmentGenerator, generator),
        AssessmentRepository(db_session),
    )

    response = service.generate_assessment(_request())

    assert response.execution is None
    assert response.result == build_assessment_result()
    generator.generate.assert_called_once()


def test_agentic_api_post_get_round_trip_persists_safe_metadata(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _, handler, evidence = _workflow()
    expected_result = build_assessment_result().model_copy(
        update={
            "external_evidence_status": ExternalEvidenceStatus.RETRIEVED,
            "source_references": [
                SourceReference(
                    document_id=evidence.document_id,
                    chunk_id=evidence.chunk_id,
                    document_title=evidence.document_title,
                )
            ],
        }
    )
    openai_client = Mock()
    openai_client.responses.create.side_effect = [
        SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="search_knowledge",
                    arguments='{"query":"human review controls","top_k":2}',
                )
            ]
        ),
        SimpleNamespace(output=[SimpleNamespace(type="message")]),
    ]
    openai_client.responses.parse.return_value = SimpleNamespace(output_parsed=expected_result)
    generator = OpenAIAssessmentGenerator(
        model="gpt-4.1-mini",
        client_provider=lambda: cast(OpenAI, openai_client),
    )
    agent = OpenAIAssessmentAgent(
        model="gpt-4.1-mini",
        generator=generator,
        client_provider=lambda: cast(OpenAI, openai_client),
    )
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="search_knowledge",
                description="Search existing knowledge.",
                arguments_model=SearchKnowledgeArguments,
                handler=handler,
            )
        ]
    )
    workflow = AgenticAssessmentWorkflow(
        agent=agent,
        tools=registry,
        max_steps=5,
        max_tool_calls=5,
        recursion_limit=25,
    )
    app.dependency_overrides[get_agentic_assessment_workflow] = lambda: workflow

    created_response = client.post("/api/v1/assessments", json=_request().model_dump(mode="json"))
    assert created_response.status_code == 200
    created = AssessmentResponse.model_validate(created_response.json())

    retrieved_response = client.get(f"/api/v1/assessments/{created.assessment_id}")
    assert retrieved_response.status_code == 200
    retrieved = AssessmentResponse.model_validate(retrieved_response.json())

    assert created.execution is not None
    assert created.execution.tools_used == ["search_knowledge"]
    assert retrieved == created
    assert handler.call_count == 1
    assert openai_client.responses.create.call_count == 2
    openai_client.responses.parse.assert_called_once()
    with session_factory() as session:
        persisted = AssessmentRepository(session).get_by_id(created.assessment_id)
    assert persisted is not None and persisted.execution_metadata is not None
