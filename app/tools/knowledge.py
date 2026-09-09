"""Read-only V3 knowledge adapters exposed through the V4 tool registry."""

from typing import cast

from pydantic import BaseModel

from app.rag.retrieval import RetrievalService
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.tools.models import (
    GetKnowledgeDocumentArguments,
    ObservedKnowledgeDocument,
    SearchKnowledgeArguments,
    ToolExecutionResult,
)
from app.tools.registry import ToolDefinition, ToolRegistry

DOCUMENT_EXCERPT_MAX_CHARS = 12_000


def build_knowledge_tool_registry(
    *,
    retrieval: RetrievalService,
    documents: KnowledgeDocumentRepository,
) -> ToolRegistry:
    """Build the complete V4 allowlist from existing V3 services."""

    def search_knowledge(raw_arguments: BaseModel) -> ToolExecutionResult:
        arguments = cast(SearchKnowledgeArguments, raw_arguments)
        evidence = tuple(retrieval.search(arguments.query, top_k=arguments.top_k))
        return ToolExecutionResult(
            tool_name="search_knowledge",
            success=True,
            summary=f"Knowledge search returned {len(evidence)} relevant chunk(s).",
            evidence=evidence,
        )

    def get_knowledge_document(raw_arguments: BaseModel) -> ToolExecutionResult:
        arguments = cast(GetKnowledgeDocumentArguments, raw_arguments)
        record = documents.get_by_id(arguments.document_id)
        if record is None:
            return ToolExecutionResult(
                tool_name="get_knowledge_document",
                success=True,
                summary="Knowledge document was not found.",
            )

        excerpt = record.content[:DOCUMENT_EXCERPT_MAX_CHARS]
        return ToolExecutionResult(
            tool_name="get_knowledge_document",
            success=True,
            summary="Knowledge document was retrieved through the read-only repository.",
            document=ObservedKnowledgeDocument(
                document_id=record.document_id,
                title=record.title,
                source_type=record.source_type,
                content_excerpt=excerpt,
                metadata=dict(record.metadata),
                truncated=len(record.content) > len(excerpt),
            ),
        )

    return ToolRegistry(
        [
            ToolDefinition(
                name="search_knowledge",
                description=(
                    "Search the existing enterprise knowledge store for evidence relevant to "
                    "the assessment. Use a focused query and a small result count."
                ),
                arguments_model=SearchKnowledgeArguments,
                handler=search_knowledge,
            ),
            ToolDefinition(
                name="get_knowledge_document",
                description=(
                    "Read a bounded excerpt of one existing knowledge document by UUID. Use it "
                    "only when a known source needs more context."
                ),
                arguments_model=GetKnowledgeDocumentArguments,
                handler=get_knowledge_document,
            ),
        ]
    )
