"""Feature-flag wiring tests that preserve V1-V5 defaults."""

from app.api.dependencies import get_assessment_rag_service, get_graph_retrieval_service
from app.core.config import Settings
from app.knowledge_graph.hybrid import HybridRAGService
from app.rag.service import RAGService


def test_graph_retrieval_dependency_is_off_by_default() -> None:
    service = get_graph_retrieval_service(
        graph=object(),  # type: ignore[arg-type]
        settings=Settings(_env_file=None),
    )

    assert service is None


def test_rag_dependency_preserves_v3_when_graph_is_disabled() -> None:
    retrieval = object()
    service = get_assessment_rag_service(
        retrieval=retrieval,  # type: ignore[arg-type]
        graph=None,
        settings=Settings(_env_file=None, RAG_ENABLED=True),
    )

    assert isinstance(service, RAGService)


def test_rag_dependency_uses_hybrid_service_only_when_graph_is_available() -> None:
    service = get_assessment_rag_service(
        retrieval=object(),  # type: ignore[arg-type]
        graph=object(),  # type: ignore[arg-type]
        settings=Settings(_env_file=None, RAG_ENABLED=True, KNOWLEDGE_GRAPH_ENABLED=True),
    )

    assert isinstance(service, HybridRAGService)
