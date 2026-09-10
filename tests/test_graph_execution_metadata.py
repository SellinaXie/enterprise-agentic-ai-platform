"""Graph retrieval metadata persistence without exposing graph source content."""

from typing import cast

from sqlalchemy.orm import Session

from app.agents.models import DeterministicExecutionMetadata
from app.models.knowledge_graph import GraphRetrievalExecutionMetadata, HybridRAGPreparation
from app.rag.context import NO_EVIDENCE_CONTEXT
from app.repositories.assessments import AssessmentRepository
from app.schemas.assessment import AssessmentRequest
from app.services.assessments import AssessmentGenerator, AssessmentService
from tests.factories import build_assessment_result


class EmptyHybridRAG:
    def prepare(self, _: AssessmentRequest) -> HybridRAGPreparation:
        return HybridRAGPreparation(
            query="synthetic query",
            evidence=(),
            context=NO_EVIDENCE_CONTEXT,
            graph_retrieval=GraphRetrievalExecutionMetadata(
                graph_retrieval_used=True,
                matched_entity_count=0,
                relationship_count=0,
                graph_depth_used=0,
                vector_evidence_count=0,
                graph_evidence_count=0,
                hybrid_evidence_count=0,
            ),
        )


class StaticGenerator:
    def generate(self, _: object) -> object:
        return build_assessment_result()


def test_deterministic_hybrid_metadata_round_trips_in_existing_jsonb_contract(
    db_session: Session,
) -> None:
    request = AssessmentRequest(
        company_name="Synthetic Bank",
        organization_description="Synthetic organization",
        industry="Banking",
        business_problem="Manual review",
        current_process="Analysts review requests",
        pain_points=["Slow review"],
        desired_outcome="Faster governed review",
        constraints=["Human approval"],
    )
    repository = AssessmentRepository(db_session)
    service = AssessmentService(
        cast(AssessmentGenerator, StaticGenerator()),
        repository,
        rag_service=EmptyHybridRAG(),
    )

    created = service.generate_assessment(request)
    retrieved = service.get_assessment(created.assessment_id)

    assert isinstance(retrieved.execution, DeterministicExecutionMetadata)
    assert retrieved.execution.graph_retrieval is not None
    assert retrieved.execution.graph_retrieval.graph_retrieval_used is True
