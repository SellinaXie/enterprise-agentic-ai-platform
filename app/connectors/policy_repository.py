"""Read-only HTTPS policy repository connector using the existing ingestion pipeline."""

import json
import logging
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.exceptions import ConnectorUnavailableError, InvalidConnectorResponseError
from app.models.knowledge import KnowledgeSourceType
from app.rag.ingestion import KnowledgeIngestionService
from app.schemas.knowledge import KnowledgeDocumentCreate

logger = logging.getLogger(__name__)


class GraphEnrichment(Protocol):
    def enrich(self, document_id: UUID) -> object: ...


class PolicyDocument(BaseModel):
    """Allowlisted upstream policy representation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_id: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=1_000_000)
    source_uri: str | None = Field(default=None, max_length=2_000)
    updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyDocumentPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[PolicyDocument]


class PolicyRepositorySyncResult(BaseModel):
    fetched: int
    ingested: int
    duplicates: int
    graph_enriched: int
    graph_failed: int
    document_ids: list[UUID]


class PolicyRepositoryConnector:
    """Fetch configured policy text and delegate processing to V3/V6 services."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        documents_path: str,
        knowledge: KnowledgeIngestionService,
        graph: GraphEnrichment | None,
        timeout_seconds: int,
        max_documents: int,
        max_response_bytes: int,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._documents_path = documents_path
        self._knowledge = knowledge
        self._graph = graph
        self._max_documents = max_documents
        self._max_response_bytes = max_response_bytes
        self._client = client or httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout_seconds,
            follow_redirects=False,
        )
        self._owns_client = client is None

    def sync(self, *, enrich_graph: bool = False) -> PolicyRepositorySyncResult:
        """Perform one bounded pull; no background access or upstream mutation occurs."""
        try:
            with self._client.stream(
                "GET", self._documents_path, params={"limit": self._max_documents}
            ) as response:
                response.raise_for_status()
                chunks = []
                received = 0
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > self._max_response_bytes:
                        raise InvalidConnectorResponseError
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            logger.warning(
                "policy_repository_fetch_failed",
                extra={"failure_type": type(exc).__name__},
            )
            raise ConnectorUnavailableError from exc
        try:
            page = PolicyDocumentPage.model_validate(json.loads(b"".join(chunks)))
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, ValueError) as exc:
            raise InvalidConnectorResponseError from exc
        if len(page.documents) > self._max_documents:
            raise InvalidConnectorResponseError

        document_ids: list[UUID] = []
        duplicates = 0
        graph_enriched = 0
        graph_failed = 0
        repository_host = urlsplit(self._base_url).hostname
        for document in page.documents:
            try:
                ingestion_request = KnowledgeDocumentCreate(
                    title=document.title,
                    source_type=KnowledgeSourceType.POLICY,
                    source_uri=document.source_uri,
                    external_id=document.external_id,
                    content=document.content,
                    metadata={
                        "connector": {
                            "type": "policy_repository",
                            "repository_host": repository_host,
                            "external_updated_at": (
                                document.updated_at.isoformat() if document.updated_at else None
                            ),
                        },
                        "upstream": document.metadata,
                        "content_trust": "untrusted_evidence",
                    },
                )
            except ValidationError as exc:
                raise InvalidConnectorResponseError from exc
            result = self._knowledge.ingest(
                ingestion_request,
                deduplicate=True,
            )
            document_ids.append(result.document.document_id)
            duplicates += int(result.duplicate)
            if enrich_graph and not result.duplicate and self._graph is not None:
                try:
                    self._graph.enrich(result.document.document_id)
                    graph_enriched += 1
                except Exception as exc:
                    graph_failed += 1
                    logger.warning(
                        "policy_repository_graph_enrichment_failed",
                        extra={"failure_type": type(exc).__name__},
                    )
        return PolicyRepositorySyncResult(
            fetched=len(page.documents),
            ingested=len(page.documents) - duplicates,
            duplicates=duplicates,
            graph_enriched=graph_enriched,
            graph_failed=graph_failed,
            document_ids=document_ids,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
