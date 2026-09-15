"""Enterprise connector API contracts."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PolicyRepositorySyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enrich_graph: bool = False


class PolicyRepositorySyncResponse(BaseModel):
    fetched: int
    ingested: int
    duplicates: int
    graph_enriched: int
    graph_failed: int
    document_ids: list[UUID]
