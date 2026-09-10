"""Higher-level upload orchestration that reuses the existing V3/V6 services."""

import json
import logging
from pathlib import PurePath
from typing import Protocol
from uuid import UUID

from fastapi import UploadFile
from pydantic import ValidationError

from app.core.exceptions import (
    ApplicationError,
    DocumentParseError,
    FileTooLargeError,
    InvalidUploadMetadataError,
)
from app.ingestion.models import (
    FileIngestionResult,
    GraphEnrichmentStatus,
    ParsedDocument,
)
from app.ingestion.router import DocumentParserRouter, sanitize_filename
from app.models.knowledge import KnowledgeSourceSegment, KnowledgeSourceType
from app.rag.ingestion import KnowledgeIngestionService
from app.schemas.knowledge import KnowledgeDocumentCreate

logger = logging.getLogger(__name__)
READ_SIZE = 64 * 1024
MAX_METADATA_CHARACTERS = 100_000


class GraphEnrichmentProtocol(Protocol):
    """Existing V6 enrichment operation used after vector ingestion commits."""

    def enrich(self, document_id: UUID) -> object: ...


class FileIngestionService:
    """Validate, parse, and adapt enterprise files into the existing V3 pipeline."""

    def __init__(
        self,
        *,
        parsers: DocumentParserRouter,
        knowledge: KnowledgeIngestionService,
        graph: GraphEnrichmentProtocol | None,
        max_upload_size_bytes: int,
    ) -> None:
        self._parsers = parsers
        self._knowledge = knowledge
        self._graph = graph
        self._max_upload_size_bytes = max_upload_size_bytes

    async def ingest_upload(
        self,
        upload: UploadFile,
        *,
        title: str | None,
        source_type: KnowledgeSourceType | None,
        metadata_json: str | None,
        enrich_graph: bool,
    ) -> FileIngestionResult:
        """Read within bounds, parse bytes, then delegate all RAG work to V3."""
        filename = sanitize_filename(upload.filename)
        data = await self._read_bounded(upload)
        parser = self._parsers.select(
            filename=filename,
            mime_type=upload.content_type,
            data=data,
        )
        try:
            parsed = parser.parse(
                data,
                filename=filename,
                mime_type=(upload.content_type or "application/octet-stream").split(";", 1)[0],
            )
        except ApplicationError:
            raise
        except Exception as exc:
            logger.warning(
                "document_parser_failed",
                extra={
                    "parser_name": type(parser).__name__,
                    "failure_type": type(exc).__name__,
                },
            )
            raise DocumentParseError from exc
        user_metadata = parse_upload_metadata(metadata_json)
        request = self._build_request(
            parsed,
            title=title,
            source_type=source_type,
            user_metadata=user_metadata,
        )
        source_segments = [
            KnowledgeSourceSegment(
                text=segment.text,
                metadata={
                    "page_number": segment.page_number,
                    "section_heading": segment.section_heading,
                },
            )
            for segment in parsed.segments
        ]
        result = self._knowledge.ingest(
            request,
            deduplicate=True,
            source_segments=source_segments,
        )
        graph_status, graph_error_code = self._enrich_graph(
            result.document.document_id,
            requested=enrich_graph,
        )
        logger.info(
            "file_ingestion_completed",
            extra={
                "document_id": str(result.document.document_id),
                "file_format": parsed.file_format.value,
                "duplicate": result.duplicate,
                "graph_enrichment_status": graph_status.value,
            },
        )
        return FileIngestionResult(
            document=result.document,
            filename=filename,
            mime_type=parsed.mime_type,
            parser=parsed.parser_name,
            extraction_method=parsed.extraction_method,
            normalized_character_count=len(result.document.content),
            chunk_count=result.chunk_count,
            duplicate=result.duplicate,
            graph_enrichment_status=graph_status,
            graph_error_code=graph_error_code,
        )

    async def _read_bounded(self, upload: UploadFile) -> bytes:
        chunks = []
        total = 0
        while True:
            remaining = self._max_upload_size_bytes - total
            chunk = await upload.read(min(READ_SIZE, remaining + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > self._max_upload_size_bytes:
                raise FileTooLargeError
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _build_request(
        parsed: ParsedDocument,
        *,
        title: str | None,
        source_type: KnowledgeSourceType | None,
        user_metadata: dict[str, object],
    ) -> KnowledgeDocumentCreate:
        resolved_title = (title or parsed.title).strip()
        if not resolved_title or len(resolved_title) > 300:
            raise InvalidUploadMetadataError
        provenance = {
            "filename": parsed.filename,
            "mime_type": parsed.mime_type,
            "file_extension": PurePath(parsed.filename).suffix.casefold(),
            "file_format": parsed.file_format.value,
            "parser_name": parsed.parser_name,
            "parser_version": parsed.parser_version,
            "extraction_method": parsed.extraction_method,
            "page_count": parsed.page_count,
            "sections": parsed.sections,
            "raw_binary_retained": False,
        }
        try:
            return KnowledgeDocumentCreate(
                title=resolved_title,
                source_type=source_type or parsed.source_type,
                content=parsed.text,
                metadata={
                    "file": provenance,
                    "parser": dict(parsed.metadata),
                    "user": user_metadata,
                    "content_trust": "untrusted_evidence",
                },
            )
        except ValidationError as exc:
            raise DocumentParseError from exc

    def _enrich_graph(
        self,
        document_id: UUID,
        *,
        requested: bool,
    ) -> tuple[GraphEnrichmentStatus, str | None]:
        if not requested:
            return GraphEnrichmentStatus.NOT_REQUESTED, None
        if self._graph is None:
            return GraphEnrichmentStatus.DISABLED, "knowledge_graph_disabled"
        try:
            self._graph.enrich(document_id)
        except ApplicationError as exc:
            logger.warning(
                "file_graph_enrichment_degraded",
                extra={"document_id": str(document_id), "error_code": exc.error_code},
            )
            return GraphEnrichmentStatus.FAILED, exc.error_code
        except Exception as exc:
            logger.warning(
                "file_graph_enrichment_degraded",
                extra={
                    "document_id": str(document_id),
                    "error_code": "graph_enrichment_failed",
                    "failure_type": type(exc).__name__,
                },
            )
            return GraphEnrichmentStatus.FAILED, "graph_enrichment_failed"
        return GraphEnrichmentStatus.COMPLETED, None


def parse_upload_metadata(value: str | None) -> dict[str, object]:
    """Parse one bounded JSON object without allowing reserved provenance overrides."""
    if value is None or not value.strip():
        return {}
    if len(value) > MAX_METADATA_CHARACTERS:
        raise InvalidUploadMetadataError
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidUploadMetadataError from exc
    if not isinstance(parsed, dict):
        raise InvalidUploadMetadataError
    return parsed
