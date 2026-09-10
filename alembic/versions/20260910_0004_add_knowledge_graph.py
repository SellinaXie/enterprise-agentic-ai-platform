"""Add the V6 relational knowledge graph.

Revision ID: 20260910_0004
Revises: 20260909_0003
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260910_0004"
down_revision: str | None = "20260909_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENTITY_TYPES = (
    "organization",
    "process",
    "system",
    "policy",
    "regulation",
    "risk",
    "data_asset",
    "ai_capability",
    "control",
    "role",
    "other",
)
RELATIONSHIP_TYPES = (
    "uses",
    "depends_on",
    "part_of",
    "governed_by",
    "affected_by",
    "creates_risk",
    "mitigated_by",
    "requires",
    "produces",
    "consumes",
    "related_to",
)


def _allowed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Create normalized entities, source mentions, and constrained relationships."""
    op.create_table(
        "knowledge_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("canonical_name", sa.String(length=300), nullable=False),
        sa.Column("normalized_name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"entity_type IN ({_allowed(ENTITY_TYPES)})",
            name=op.f("ck_knowledge_entities_knowledge_entity_type_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_entities")),
        sa.UniqueConstraint(
            "entity_type",
            "normalized_name",
            name="uq_knowledge_entities_type_normalized_name",
        ),
    )
    op.create_index(
        "ix_knowledge_entities_normalized_name",
        "knowledge_entities",
        ["normalized_name"],
    )
    op.create_index(
        "ix_knowledge_entities_entity_type",
        "knowledge_entities",
        ["entity_type"],
    )

    op.create_table(
        "knowledge_entity_mentions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mention_text", sa.String(length=500), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="knowledge_entity_mentions_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["knowledge_entities.id"],
            name=op.f("fk_knowledge_entity_mentions_entity_id_knowledge_entities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_entity_mentions_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["knowledge_chunks.id"],
            name=op.f("fk_knowledge_entity_mentions_chunk_id_knowledge_chunks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_entity_mentions")),
        sa.UniqueConstraint(
            "entity_id",
            "chunk_id",
            name="uq_knowledge_entity_mentions_entity_chunk",
        ),
    )
    for column in ("entity_id", "document_id", "chunk_id"):
        op.create_index(
            f"ix_knowledge_entity_mentions_{column}",
            "knowledge_entity_mentions",
            [column],
        )

    op.create_table(
        "knowledge_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_entity_id <> target_entity_id",
            name="knowledge_relationships_no_self_edge",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="knowledge_relationships_confidence_range",
        ),
        sa.CheckConstraint(
            f"relationship_type IN ({_allowed(RELATIONSHIP_TYPES)})",
            name=op.f("ck_knowledge_relationships_knowledge_relationship_type_values"),
        ),
        sa.ForeignKeyConstraint(
            ["source_entity_id"],
            ["knowledge_entities.id"],
            name=op.f("fk_knowledge_relationships_source_entity_id_knowledge_entities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_entity_id"],
            ["knowledge_entities.id"],
            name=op.f("fk_knowledge_relationships_target_entity_id_knowledge_entities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_chunk_id"],
            ["knowledge_chunks.id"],
            name=op.f("fk_knowledge_relationships_source_chunk_id_knowledge_chunks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_relationships")),
        sa.UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            "source_chunk_id",
            name="uq_knowledge_relationships_source_target_type_chunk",
        ),
    )
    for column in (
        "source_entity_id",
        "target_entity_id",
        "relationship_type",
        "source_chunk_id",
    ):
        op.create_index(
            f"ix_knowledge_relationships_{column}",
            "knowledge_relationships",
            [column],
        )


def downgrade() -> None:
    """Remove only the V6 graph tables in dependency-safe order."""
    for column in (
        "source_chunk_id",
        "relationship_type",
        "target_entity_id",
        "source_entity_id",
    ):
        op.drop_index(
            f"ix_knowledge_relationships_{column}",
            table_name="knowledge_relationships",
        )
    op.drop_table("knowledge_relationships")

    for column in ("chunk_id", "document_id", "entity_id"):
        op.drop_index(
            f"ix_knowledge_entity_mentions_{column}",
            table_name="knowledge_entity_mentions",
        )
    op.drop_table("knowledge_entity_mentions")

    op.drop_index("ix_knowledge_entities_entity_type", table_name="knowledge_entities")
    op.drop_index("ix_knowledge_entities_normalized_name", table_name="knowledge_entities")
    op.drop_table("knowledge_entities")
