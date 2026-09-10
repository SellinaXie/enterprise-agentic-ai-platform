"""V6 API feature flag, graph tool permissions, and prompt-context tests."""

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.evidence_prompt import build_evidence_brief_input
from app.agents.multi_agent_models import MultiAgentName
from app.api.dependencies import get_graph_enrichment_service
from app.core.exceptions import KnowledgeGraphUnavailableError
from app.models.knowledge_graph import GraphNeighborhood, KnowledgeGraphEnrichmentResult
from app.schemas.assessment import AssessmentRequest
from app.tools.knowledge import build_knowledge_tool_registry
from app.tools.permissions import AgentToolPermissions


class EmptyRetrieval:
    def search(self, *_: object, **__: object) -> list[object]:
        return []


class EmptyDocuments:
    def get_by_id(self, _: object) -> None:
        return None


class EmptyGraph:
    def search(self, query: str, **_: object) -> GraphNeighborhood:
        return GraphNeighborhood.empty(query)


class UnavailableGraph:
    def search(self, query: str, **_: object) -> GraphNeighborhood:
        del query
        raise KnowledgeGraphUnavailableError


class StubEnrichment:
    def enrich(self, document_id: object) -> KnowledgeGraphEnrichmentResult:
        return KnowledgeGraphEnrichmentResult(
            document_id=document_id,  # type: ignore[arg-type]
            entity_count=3,
            relationship_count=2,
        )


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Synthetic Bank",
        organization_description="Synthetic test organization",
        industry="Banking",
        business_problem="Manual loan review",
        current_process="Reviewers inspect applications",
        pain_points=["Slow review"],
        desired_outcome="Faster governed review",
        constraints=["Human approval required"],
    )


def test_graph_enrichment_endpoint_is_disabled_by_default(client: TestClient) -> None:
    response = client.post(f"/api/v1/knowledge/documents/{uuid4()}/graph")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "knowledge_graph_disabled"


def test_graph_enrichment_endpoint_returns_typed_counts(
    app: FastAPI,
    client: TestClient,
) -> None:
    document_id = uuid4()
    app.dependency_overrides[get_graph_enrichment_service] = lambda: StubEnrichment()

    response = client.post(f"/api/v1/knowledge/documents/{document_id}/graph")

    assert response.status_code == 200
    assert response.json() == {
        "document_id": str(document_id),
        "entity_count": 3,
        "relationship_count": 2,
        "status": "completed",
    }


def test_v4_registry_is_unchanged_and_v6_registry_adds_one_graph_tool() -> None:
    base = build_knowledge_tool_registry(
        retrieval=EmptyRetrieval(),  # type: ignore[arg-type]
        documents=EmptyDocuments(),  # type: ignore[arg-type]
    )
    graph = build_knowledge_tool_registry(
        retrieval=EmptyRetrieval(),  # type: ignore[arg-type]
        documents=EmptyDocuments(),  # type: ignore[arg-type]
        graph=EmptyGraph(),  # type: ignore[arg-type]
    )

    assert base.names == ("search_knowledge", "get_knowledge_document")
    assert graph.names == (
        "search_knowledge",
        "get_knowledge_document",
        "search_knowledge_graph",
    )
    graph_schema = graph.schemas()[-1]
    assert graph_schema["strict"] is True
    assert set(graph_schema["parameters"]["required"]) == {
        "query",
        "max_depth",
        "entity_types",
    }


def test_graph_tool_is_available_only_to_evidence_agent() -> None:
    registry = build_knowledge_tool_registry(
        retrieval=EmptyRetrieval(),  # type: ignore[arg-type]
        documents=EmptyDocuments(),  # type: ignore[arg-type]
        graph=EmptyGraph(),  # type: ignore[arg-type]
    )
    permissions = AgentToolPermissions()
    arguments = {"query": "Loan Portal", "max_depth": 2, "entity_types": None}

    result, _, _ = permissions.execute(
        agent=MultiAgentName.EVIDENCE,
        registry=registry,
        name="search_knowledge_graph",
        raw_arguments=arguments,
    )
    denied, _, _ = permissions.execute(
        agent=MultiAgentName.ARCHITECTURE,
        registry=registry,
        name="search_knowledge_graph",
        raw_arguments=arguments,
    )

    assert result.success is True
    assert result.graph_retrieval is not None
    assert denied.error_code == "unauthorized_tool"


def test_graph_tool_failure_returns_safe_degraded_metadata() -> None:
    registry = build_knowledge_tool_registry(
        retrieval=EmptyRetrieval(),  # type: ignore[arg-type]
        documents=EmptyDocuments(),  # type: ignore[arg-type]
        graph=UnavailableGraph(),  # type: ignore[arg-type]
    )

    result, _, _ = registry.execute(
        "search_knowledge_graph",
        {"query": "Loan Portal", "max_depth": 2, "entity_types": None},
    )

    assert result.success is False
    assert result.error_code == "knowledge_graph_unavailable"
    assert result.graph_retrieval is not None
    assert result.graph_retrieval.degraded_graph_mode is True


def test_evidence_prompt_includes_observed_graph_without_chain_of_thought() -> None:
    prompt = build_evidence_brief_input(
        request=_request(),
        evidence=[],
        documents=[],
        graph_neighborhoods=[GraphNeighborhood.empty("Loan Portal")],
    )

    assert '"observed_graph"' in prompt
    assert '"query": "Loan Portal"' in prompt
    assert "chain-of-thought" not in prompt.lower()
