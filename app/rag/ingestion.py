"""Atomic normalization, chunking, embedding, and persistence pipeline."""

import hashlib
import logging
from typing import NoReturn
from uuid import UUID, uuid4

from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from app.core.exceptions import (
    ApplicationError,
    EmptyKnowledgeDocumentError,
    InvalidEmbeddingError,
    KnowledgeDocumentNotFoundError,
    KnowledgePersistenceError,
    KnowledgeStoreUnavailableError,
)
from app.models.knowledge import (
    EmbeddedChunk,
    KnowledgeDocumentRecord,
    KnowledgeIngestionResult,
)
from app.rag.chunking import chunk_text, normalize_text
from app.rag.embeddings import EmbeddingsService
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.schemas.knowledge import KnowledgeDocumentCreate

logger = logging.getLogger(__name__)


class KnowledgeIngestionService:
    """Coordinate one transactional plain-text ingestion operation."""

    def __init__(
        self,
        *,
        documents: KnowledgeDocumentRepository,
        chunks: KnowledgeChunkRepository,
        embeddings: EmbeddingsService,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self._documents = documents
        self._chunks = chunks
        self._embeddings = embeddings
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def ingest(self, request: KnowledgeDocumentCreate) -> KnowledgeIngestionResult:
        """Normalize and persist a document and all embedded chunks atomically."""
        document_id = uuid4()
        log_context = {"document_id": str(document_id)}
        logger.info("document_ingestion_started", extra=log_context)

        normalized = normalize_text(request.content)
        if not normalized:
            raise EmptyKnowledgeDocumentError
        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        try:
            document = self._documents.create(
                document_id=document_id,
                title=request.title,
                source_type=request.source_type,
                source_uri=request.source_uri,
                external_id=request.external_id,
                content=normalized,
                metadata=request.metadata,
                content_hash=content_hash,
            )
            logger.info("document_stored", extra=log_context)

            text_chunks = chunk_text(
                normalized,
                chunk_size=self._chunk_size,
                overlap=self._chunk_overlap,
            )
            if not text_chunks:
                raise EmptyKnowledgeDocumentError
            logger.info(
                "chunking_completed",
                extra={**log_context, "chunk_count": len(text_chunks)},
            )

            vectors = self._embeddings.embed_texts([chunk.content for chunk in text_chunks])
            if len(vectors) != len(text_chunks):
                raise InvalidEmbeddingError
            logger.info(
                "embeddings_generated",
                extra={**log_context, "chunk_count": len(vectors)},
            )
            embedded_chunks = [
                EmbeddedChunk(
                    chunk_index=chunk.index,
                    content=chunk.content,
                    embedding=vector,
                    metadata={"content_hash": hashlib.sha256(chunk.content.encode()).hexdigest()},
                )
                for chunk, vector in zip(text_chunks, vectors, strict=True)
            ]
            self._chunks.bulk_create(document_id=document_id, chunks=embedded_chunks)
            self._documents.commit()
            logger.info(
                "chunks_persisted",
                extra={**log_context, "chunk_count": len(embedded_chunks)},
            )
            return KnowledgeIngestionResult(
                document=document,
                chunk_count=len(embedded_chunks),
            )
        except ApplicationError:
            self._documents.rollback()
            raise
        except SQLAlchemyError as exc:
            self._documents.rollback()
            self._raise_database_error(exc)

    def get_document(self, document_id: UUID) -> KnowledgeDocumentRecord:
        """Return one document or raise a typed not-found error."""
        try:
            document = self._documents.get_by_id(document_id)
        except SQLAlchemyError as exc:
            self._raise_database_error(exc)
        if document is None:
            raise KnowledgeDocumentNotFoundError
        return document

    @staticmethod
    def _raise_database_error(exc: SQLAlchemyError) -> NoReturn:
        logger.error(
            "knowledge_database_failure",
            extra={"database_error_type": type(exc).__name__},
        )
        if isinstance(exc, (OperationalError, ProgrammingError)):
            raise KnowledgeStoreUnavailableError from exc
        raise KnowledgePersistenceError from exc
