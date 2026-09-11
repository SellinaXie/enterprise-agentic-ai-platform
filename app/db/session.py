"""Synchronous SQLAlchemy engine and session construction."""

from collections.abc import Iterator
from contextlib import suppress
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import DatabaseNotConfiguredError, DatabaseUnavailableError

_created_engines: set[Engine] = set()


def get_database_url(settings: Settings) -> str:
    """Return the configured URL without logging or otherwise exposing it."""
    if settings.database_url is None:
        raise DatabaseNotConfiguredError

    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        raise DatabaseNotConfiguredError
    return database_url


@lru_cache
def get_engine(database_url: str, connect_timeout_seconds: int = 5) -> Engine:
    """Create one lazy synchronous engine per configured database URL."""
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    elif database_url.startswith("postgresql"):
        connect_args = {"connect_timeout": connect_timeout_seconds}
    else:
        connect_args = {}
    engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    _created_engines.add(engine)
    return engine


@lru_cache
def get_session_factory(
    database_url: str,
    connect_timeout_seconds: int = 5,
) -> sessionmaker[Session]:
    """Return a session factory with explicit transaction control."""
    return sessionmaker(
        bind=get_engine(database_url, connect_timeout_seconds),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db_session(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[Session]:
    """Yield a request-scoped session; services own commit boundaries."""
    try:
        session = get_session_factory(
            get_database_url(settings), settings.database_connect_timeout_seconds
        )()
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError from exc
    try:
        yield session
    except Exception:
        with suppress(SQLAlchemyError):
            session.rollback()
        raise
    finally:
        session.close()


def dispose_database_resources() -> None:
    """Dispose every engine created by this process and clear cached factories."""
    for engine in tuple(_created_engines):
        engine.dispose()
    _created_engines.clear()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
