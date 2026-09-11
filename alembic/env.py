"""Alembic environment for the PostgreSQL application-state schema."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import Settings
from app.db.base import Base
from app.db.models import (  # noqa: F401
    AssessmentModel,
    AssessmentRuntimeStateModel,
    HumanReviewEventModel,
    KnowledgeChunkModel,
    KnowledgeDocumentModel,
)
from app.db.session import get_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configured_database_url() -> str:
    """Load the migration URL without placing credentials in alembic.ini or logs."""
    return get_database_url(Settings())


def run_migrations_offline() -> None:
    """Render migration SQL without opening a database connection."""
    context.configure(
        url=_configured_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the explicitly configured application database."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _configured_database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
