"""Independent tests for the V4 approved tool boundary."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

from app.core.exceptions import EmbeddingProviderError
from app.models.knowledge import (
    KnowledgeDocumentRecord,
    KnowledgeSourceType,
    RetrievedEvidence,
)
from app.rag.retrieval import RetrievalService
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.tools.knowledge import DOCUMENT_EXCERPT_MAX_CHARS, build_knowledge_tool_registry
from app.tools.models import SearchKnowledgeArguments, ToolExecutionResult
from app.tools.registry import ToolDefinition, ToolRegistry


def _evidence() -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Synthetic policy",
        content="Human review is required.",
        similarity_score=0.91,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )


def _registry(
    retrieval: Mock | None = None,
    documents: Mock | None = None,
) -> tuple[ToolRegistry, Mock, Mock]:
    retrieval = retrieval or Mock(spec=RetrievalService)
    documents = documents or Mock(spec=KnowledgeDocumentRepository)
    return (
        build_knowledge_tool_registry(
            retrieval=cast(RetrievalService, retrieval),
            documents=cast(KnowledgeDocumentRepository, documents),
        ),
        retrieval,
        documents,
    )


def test_registry_exports_strict_closed_function_schemas() -> None:
    registry, _, _ = _registry()

    schemas = registry.schemas()

    assert registry.names == ("search_knowledge", "get_knowledge_document")
    assert all(schema["type"] == "function" for schema in schemas)
    assert all(schema["strict"] is True for schema in schemas)
    assert all(schema["parameters"]["additionalProperties"] is False for schema in schemas)
    assert schemas[0]["parameters"]["required"] == ["query", "top_k"]


def test_unknown_tool_is_rejected_before_execution() -> None:
    registry, retrieval, documents = _registry()

    result, _, _ = registry.execute("run_shell", {"command": "whoami"})

    assert result.success is False
    assert result.error_code == "unknown_tool"
    retrieval.search.assert_not_called()
    documents.get_by_id.assert_not_called()


def test_invalid_tool_arguments_are_rejected() -> None:
    registry, retrieval, _ = _registry()

    result, _, _ = registry.execute("search_knowledge", {"query": "", "top_k": 100})

    assert result.success is False
    assert result.error_code == "invalid_tool_arguments"
    retrieval.search.assert_not_called()


def test_identical_tool_call_reuses_execution_cache() -> None:
    handler = Mock(
        return_value=ToolExecutionResult(
            tool_name="search_knowledge",
            success=True,
            summary="No results.",
        )
    )
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="search_knowledge",
                description="Search.",
                arguments_model=SearchKnowledgeArguments,
                handler=handler,
            )
        ]
    )
    cache: dict[str, ToolExecutionResult] = {}

    first, first_fingerprint, _ = registry.execute(
        "search_knowledge", {"query": "policy", "top_k": 3}, cache=cache
    )
    second, second_fingerprint, _ = registry.execute(
        "search_knowledge", {"top_k": 3, "query": "policy"}, cache=cache
    )

    assert first.cached is False
    assert second.cached is True
    assert first_fingerprint == second_fingerprint
    handler.assert_called_once()


def test_search_knowledge_reuses_v3_retrieval_and_allows_empty_results() -> None:
    evidence = _evidence()
    registry, retrieval, _ = _registry()
    retrieval.search.side_effect = [[evidence], []]

    found, _, _ = registry.execute("search_knowledge", {"query": "policy", "top_k": 2})
    empty, _, _ = registry.execute("search_knowledge", {"query": "other", "top_k": 1})

    assert found.success is True
    assert found.evidence == (evidence,)
    assert empty.success is True
    assert empty.evidence == ()
    retrieval.search.assert_any_call("policy", top_k=2)


def test_search_knowledge_normalizes_retrieval_failure() -> None:
    registry, retrieval, _ = _registry()
    retrieval.search.side_effect = EmbeddingProviderError

    result, _, _ = registry.execute("search_knowledge", {"query": "policy", "top_k": 2})

    assert result.success is False
    assert result.error_code == "embedding_provider_error"
    assert "temporarily unavailable" in result.summary


def test_get_knowledge_document_found_not_found_and_invalid_id() -> None:
    record = KnowledgeDocumentRecord(
        document_id=uuid4(),
        title="Synthetic manual",
        source_type=KnowledgeSourceType.SYNTHETIC,
        source_uri=None,
        external_id=None,
        content="x" * (DOCUMENT_EXCERPT_MAX_CHARS + 10),
        metadata={"synthetic": True},
        content_hash="a" * 64,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    registry, _, documents = _registry()
    documents.get_by_id.side_effect = [record, None]

    found, _, _ = registry.execute(
        "get_knowledge_document", {"document_id": str(record.document_id)}
    )
    missing, _, _ = registry.execute("get_knowledge_document", {"document_id": str(uuid4())})
    invalid, _, _ = registry.execute("get_knowledge_document", {"document_id": "bad"})

    assert found.success is True
    assert found.document is not None
    assert len(found.document.content_excerpt) == DOCUMENT_EXCERPT_MAX_CHARS
    assert found.document.truncated is True
    assert missing.success is True
    assert missing.document is None
    assert invalid.success is False
    assert invalid.error_code == "invalid_tool_arguments"
