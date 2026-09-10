"""Read-only V3 knowledge adapters exposed through the V4 tool registry."""

from typing import cast

from pydantic import BaseModel

from app.core.exceptions import ApplicationError
from app.knowledge_graph.retrieval import GraphRetrievalService
from app.models.knowledge_graph import GraphRetrievalExecutionMetadata
from app.rag.retrieval import RetrievalService
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.tools.models import (
    GetKnowledgeDocumentArguments,
    ObservedKnowledgeDocument,
    SearchKnowledgeArguments,
    SearchKnowledgeGraphArguments,
    ToolExecutionResult,
)
from app.tools.registry import ToolDefinition, ToolRegistry

DOCUMENT_EXCERPT_MAX_CHARS = 12_000


def build_knowledge_tool_registry(
    *,
    retrieval: RetrievalService,
    documents: KnowledgeDocumentRepository,
    graph: GraphRetrievalService | None = None,
) -> ToolRegistry:
    """Build V4's two tools, optionally adding the Evidence-only V6 graph tool."""

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

    definitions = [
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
    if graph is not None:

        def search_knowledge_graph(raw_arguments: BaseModel) -> ToolExecutionResult:
            arguments = cast(SearchKnowledgeGraphArguments, raw_arguments)
            try:
                neighborhood = graph.search(
                    arguments.query,
                    max_depth=arguments.max_depth,
                    entity_types=arguments.entity_types,
                )
            except ApplicationError as exc:
                return ToolExecutionResult(
                    tool_name="search_knowledge_graph",
                    success=False,
                    summary=exc.public_message,
                    graph_retrieval=GraphRetrievalExecutionMetadata(
                        degraded_graph_mode=True,
                        graph_error_code=exc.error_code,
                    ),
                    error_code=exc.error_code,
                )
            metadata = GraphRetrievalExecutionMetadata(
                graph_retrieval_used=True,
                matched_entity_count=len(neighborhood.matched_entities),
                relationship_count=len(neighborhood.relationships),
                graph_depth_used=neighborhood.depth_used,
                graph_evidence_count=len(neighborhood.evidence),
                hybrid_evidence_count=len(neighborhood.evidence),
            )
            return ToolExecutionResult(
                tool_name="search_knowledge_graph",
                success=True,
                summary=(
                    "Knowledge graph search returned "
                    f"{len(neighborhood.matched_entities)} matched entity/entities and "
                    f"{len(neighborhood.relationships)} relationship(s)."
                ),
                evidence=tuple(neighborhood.evidence),
                graph_neighborhood=neighborhood,
                graph_retrieval=metadata,
            )

        definitions.append(
            ToolDefinition(
                name="search_knowledge_graph",
                description=(
                    "Find known enterprise entities and traverse a small, source-grounded "
                    "relationship neighborhood. Use only for relationship-aware evidence."
                ),
                arguments_model=SearchKnowledgeGraphArguments,
                handler=search_knowledge_graph,
            )
        )
    return ToolRegistry(definitions)
