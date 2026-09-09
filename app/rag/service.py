"""RAG preparation boundary used by assessment orchestration."""

import logging

from app.models.knowledge import RAGPreparation
from app.rag.context import build_rag_context
from app.rag.retrieval import RetrievalService, build_retrieval_query
from app.schemas.assessment import AssessmentRequest

logger = logging.getLogger(__name__)


class RAGService:
    """Prepare a retrieval query, ranked evidence, and controlled model context."""

    def __init__(self, retrieval: RetrievalService) -> None:
        self._retrieval = retrieval

    def prepare(self, request: AssessmentRequest) -> RAGPreparation:
        query = build_retrieval_query(request)
        evidence = self._retrieval.search(query)
        context = build_rag_context(evidence)
        logger.info("rag_context_built", extra={"retrieval_count": len(evidence)})
        return RAGPreparation(query=query, evidence=tuple(evidence), context=context)
