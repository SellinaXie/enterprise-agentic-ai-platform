"""Deterministic query construction and vector retrieval service."""

import logging
from contextlib import suppress
from uuid import UUID

from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from app.core.exceptions import KnowledgePersistenceError, KnowledgeStoreUnavailableError
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.rag.embeddings import EmbeddingsService
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.schemas.assessment import AssessmentRequest

logger = logging.getLogger(__name__)


def build_retrieval_query(request: AssessmentRequest) -> str:
    """Construct a transparent search query from validated assessment input."""
    fields = (
        ("Company", request.company_name),
        ("Organization", request.organization_description),
        ("Industry", request.industry),
        ("Business problem", request.business_problem),
        ("Current process", request.current_process),
        ("Pain points", "; ".join(request.pain_points) if request.pain_points else None),
        ("Desired outcome", request.desired_outcome),
        ("Constraints", "; ".join(request.constraints) if request.constraints else None),
    )
    return "\n".join(f"{label}: {value}" for label, value in fields if value)


class RetrievalService:
    """Embed queries and return ranked, attributed evidence."""

    def __init__(
        self,
        *,
        chunks: KnowledgeChunkRepository,
        embeddings: EmbeddingsService,
        top_k: int,
        similarity_threshold: float,
    ) -> None:
        self._chunks = chunks
        self._embeddings = embeddings
        self._top_k = top_k
        self._similarity_threshold = similarity_threshold

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        source_type: KnowledgeSourceType | None = None,
        document_id: UUID | None = None,
    ) -> list[RetrievedEvidence]:
        """Return cosine-ranked chunks that meet the configured threshold."""
        logger.info("retrieval_started")
        query_embedding = self._embeddings.embed_texts([query])[0]
        resolved_top_k = top_k or self._top_k
        resolved_threshold = (
            self._similarity_threshold if similarity_threshold is None else similarity_threshold
        )
        try:
            evidence = self._chunks.search_similar(
                query_embedding,
                limit=resolved_top_k,
                similarity_threshold=resolved_threshold,
                source_type=source_type,
                document_id=document_id,
            )
        except (OperationalError, ProgrammingError) as exc:
            with suppress(SQLAlchemyError):
                self._chunks.rollback()
            logger.error("retrieval_failure", extra={"database_error_type": type(exc).__name__})
            raise KnowledgeStoreUnavailableError from exc
        except SQLAlchemyError as exc:
            with suppress(SQLAlchemyError):
                self._chunks.rollback()
            logger.error("retrieval_failure", extra={"database_error_type": type(exc).__name__})
            raise KnowledgePersistenceError from exc

        unique_evidence: dict[UUID, RetrievedEvidence] = {}
        for item in evidence:
            if item.similarity_score >= resolved_threshold:
                unique_evidence.setdefault(item.chunk_id, item)
        ranked_evidence = sorted(
            unique_evidence.values(),
            key=lambda item: (-item.similarity_score, str(item.chunk_id)),
        )[:resolved_top_k]

        if ranked_evidence:
            logger.info("retrieval_completed", extra={"retrieval_count": len(ranked_evidence)})
        else:
            logger.info("retrieval_returned_zero_results", extra={"retrieval_count": 0})
        return ranked_evidence
