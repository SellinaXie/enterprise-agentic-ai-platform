"""Controlled formatting for retrieved, untrusted source evidence."""

from app.models.knowledge import RetrievedEvidence

NO_EVIDENCE_CONTEXT = "EXTERNAL_KNOWLEDGE_STATUS: NO_RELEVANT_EXTERNAL_EVIDENCE_RETRIEVED"


def build_rag_context(evidence: list[RetrievedEvidence]) -> str:
    """Format ranked chunks with stable source boundaries and identifiers."""
    if not evidence:
        return NO_EVIDENCE_CONTEXT

    sections = ["EXTERNAL_KNOWLEDGE_STATUS: RELEVANT_EVIDENCE_RETRIEVED"]
    for rank, item in enumerate(evidence, start=1):
        sections.append(
            "\n".join(
                (
                    f"BEGIN_SOURCE_{rank}",
                    f"Rank: {rank}",
                    f"Document: {item.document_title}",
                    f"Document ID: {item.document_id}",
                    f"Chunk ID: {item.chunk_id}",
                    f"Source type: {item.source_type.value}",
                    f"Similarity: {item.similarity_score:.6f}",
                    "Content:",
                    item.content,
                    f"END_SOURCE_{rank}",
                )
            )
        )
    return "\n\n".join(sections)
