"""Provenance-preserving V6 GraphRAG context construction."""

from app.models.knowledge import RetrievalSource, RetrievedEvidence
from app.models.knowledge_graph import GraphNeighborhood
from app.rag.context import NO_EVIDENCE_CONTEXT


def build_hybrid_rag_context(
    evidence: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    neighborhood: GraphNeighborhood,
) -> str:
    """Separate vector relevance, graph relationships, and supporting source text."""
    if not evidence and not neighborhood.relationships:
        return NO_EVIDENCE_CONTEXT

    vector_items = [
        item
        for item in evidence
        if item.retrieval_source in {RetrievalSource.VECTOR, RetrievalSource.BOTH}
    ]
    sections = ["EXTERNAL_KNOWLEDGE_STATUS: RELEVANT_HYBRID_EVIDENCE_RETRIEVED"]
    sections.append("VECTOR EVIDENCE")
    if vector_items:
        for rank, item in enumerate(vector_items, start=1):
            sections.append(
                "\n".join(
                    (
                        f"Vector rank: {rank}",
                        f"Document: {item.document_title}",
                        f"Document ID: {item.document_id}",
                        f"Chunk ID: {item.chunk_id}",
                        f"Retrieval source: {item.retrieval_source.value}",
                        f"Similarity: {item.similarity_score:.6f}",
                    )
                )
            )
    else:
        sections.append("No vector evidence available.")

    sections.append("GRAPH RELATIONSHIPS")
    if neighborhood.relationships:
        for rank, relationship in enumerate(neighborhood.relationships, start=1):
            sections.append(
                "\n".join(
                    (
                        f"BEGIN_GRAPH_RELATIONSHIP_{rank}",
                        f"Entity: {relationship.source_entity_name}",
                        "Relationship: "
                        f"{relationship.source_entity_name} → "
                        f"{relationship.relationship_type.value} → "
                        f"{relationship.target_entity_name}",
                        f"Description: {relationship.description or 'Not supplied'}",
                        f"Confidence: {relationship.confidence:.3f}",
                        f"Supported by document: {relationship.source_document_id}",
                        f"Supported by chunk: {relationship.source_chunk_id}",
                        f"END_GRAPH_RELATIONSHIP_{rank}",
                    )
                )
            )
    else:
        sections.append("No source-grounded graph relationships matched.")

    sections.append("SOURCE EVIDENCE")
    for rank, item in enumerate(evidence, start=1):
        sections.append(
            "\n".join(
                (
                    f"BEGIN_HYBRID_SOURCE_{rank}",
                    f"Document: {item.document_title}",
                    f"Document ID: {item.document_id}",
                    f"Chunk ID: {item.chunk_id}",
                    f"Source type: {item.source_type.value}",
                    f"Retrieval source: {item.retrieval_source.value}",
                    "Content:",
                    item.content,
                    f"END_HYBRID_SOURCE_{rank}",
                )
            )
        )
    return "\n\n".join(sections)
