"""Safely report versions from the dedicated PostgreSQL integration database."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError


def _database_identity(url: URL) -> tuple[str, int, str]:
    """Return a credential-free identity for database target comparisons."""
    return (
        (url.host or "localhost").lower(),
        url.port or 5432,
        (url.database or "").lower(),
    )


def validated_test_database_url(environment: Mapping[str, str] = os.environ) -> str:
    """Reject non-test, maintenance, production-looking, or application databases."""
    raw_url = environment.get("TEST_DATABASE_URL", "").strip()
    if not raw_url:
        raise ValueError("TEST_DATABASE_URL is required")

    try:
        test_url = make_url(raw_url)
    except ArgumentError as exc:
        raise ValueError("TEST_DATABASE_URL must be a valid SQLAlchemy URL") from exc

    if test_url.get_backend_name() != "postgresql":
        raise ValueError("TEST_DATABASE_URL must use PostgreSQL")

    database_name = (test_url.database or "").lower()
    if not database_name or "test" not in database_name:
        raise ValueError("TEST_DATABASE_URL database name must contain 'test'")
    if database_name in {"postgres", "template0", "template1"}:
        raise ValueError("TEST_DATABASE_URL cannot use a maintenance database")
    if "prod" in database_name or "production" in database_name:
        raise ValueError("TEST_DATABASE_URL cannot use a production-looking database")

    application_raw_url = environment.get("DATABASE_URL", "").strip()
    if application_raw_url:
        try:
            application_url = make_url(application_raw_url)
        except ArgumentError:
            application_url = None
        if (
            application_url is not None
            and application_url.get_backend_name() == "postgresql"
            and _database_identity(application_url) == _database_identity(test_url)
        ):
            raise ValueError("TEST_DATABASE_URL must not point to DATABASE_URL")

    return raw_url


def main() -> int:
    """Connect, confirm the target, enable pgvector, and print safe version details."""
    try:
        database_url = validated_test_database_url()
    except ValueError as exc:
        print(f"PostgreSQL probe configuration rejected: {exc}", file=sys.stderr)
        return 2

    expected_database = (make_url(database_url).database or "").lower()
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.begin() as connection:
            connected_database = connection.execute(text("SELECT current_database()"))
            connected_database = connected_database.scalar_one().lower()
            if connected_database != expected_database or "test" not in connected_database:
                raise ValueError("connected database did not pass the dedicated-test guard")
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            postgresql_version = connection.execute(
                text("SELECT current_setting('server_version')")
            ).scalar_one()
            pgvector_version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one()
    except (SQLAlchemyError, ValueError) as exc:
        print(f"PostgreSQL probe failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(f"PostgreSQL {postgresql_version}")
    print(f"pgvector {pgvector_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
