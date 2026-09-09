"""Deterministic synthetic knowledge and embeddings for V3 tests."""

import math

from app.models.knowledge import KnowledgeSourceType
from app.schemas.knowledge import KnowledgeDocumentCreate


def build_synthetic_knowledge_corpus() -> list[KnowledgeDocumentCreate]:
    """Return small fictional sources that do not represent real policy or regulation."""
    return [
        KnowledgeDocumentCreate(
            title="Synthetic AI Governance Policy",
            source_type=KnowledgeSourceType.SYNTHETIC,
            content=(
                "Synthetic test policy only. AI governance requires documented ownership, "
                "risk classification, approval records, monitoring, and human escalation for "
                "high-impact recommendations. This is not a real company policy."
            ),
            metadata={"topic": "governance", "synthetic": True},
        ),
        KnowledgeDocumentCreate(
            title="Synthetic Financial Services Compliance Workflow",
            source_type=KnowledgeSourceType.SYNTHETIC,
            content=(
                "Synthetic test workflow only. Compliance review requires an authorized reviewer "
                "to inspect the supporting evidence before a regulated lending decision is final. "
                "The workflow retains an audit record and routes exceptions for manual review."
            ),
            metadata={"topic": "compliance", "synthetic": True},
        ),
        KnowledgeDocumentCreate(
            title="Synthetic Enterprise RAG Architecture Guide",
            source_type=KnowledgeSourceType.SYNTHETIC,
            content=(
                "Synthetic architecture guidance only. A retrieval pipeline separates source "
                "documents, normalized chunks, embeddings, vector search, and controlled model "
                "context so that evidence provenance remains observable."
            ),
            metadata={"topic": "architecture", "synthetic": True},
        ),
        KnowledgeDocumentCreate(
            title="Synthetic Human-in-the-loop Risk Policy",
            source_type=KnowledgeSourceType.SYNTHETIC,
            content=(
                "Synthetic risk policy only. Human-in-the-loop review is required when an "
                "automated recommendation could materially affect a customer. Reviewers can "
                "reject output and record the reason for escalation."
            ),
            metadata={"topic": "human_oversight", "synthetic": True},
        ),
    ]


class DeterministicEmbeddingsService:
    """Map distinguishable test topics to deterministic normalized vectors."""

    def __init__(self, dimension: int = 1536) -> None:
        self.dimension = dimension
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        if "governance" in lowered:
            components = [0.92, 0.08, 0.0]
        elif "compliance" in lowered or "regulated lending" in lowered:
            components = [1.0, 0.0, 0.0]
        elif "rag architecture" in lowered or "retrieval pipeline" in lowered:
            components = [0.0, 1.0, 0.0]
        elif "human-in-the-loop" in lowered or "human oversight" in lowered:
            components = [0.75, 0.15, 0.10]
        else:
            components = [0.0, 0.0, 1.0]

        norm = math.sqrt(sum(value * value for value in components))
        vector = [value / norm for value in components]
        return (vector + [0.0] * self.dimension)[: self.dimension]
