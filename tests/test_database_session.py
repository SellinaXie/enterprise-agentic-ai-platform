"""Database URL adaptation tests."""

from app.core.config import Settings
from app.db.session import get_database_url


def test_hosted_postgres_url_selects_installed_psycopg_driver() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://user:password@database/enterprise_ai",
        PROVIDER_REQUIRED=False,
    )

    assert get_database_url(settings) == (
        "postgresql+psycopg://user:password@database/enterprise_ai"
    )


def test_explicit_sqlalchemy_driver_is_preserved() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg://user:password@database/enterprise_ai",
        PROVIDER_REQUIRED=False,
    )

    assert get_database_url(settings) == (
        "postgresql+psycopg://user:password@database/enterprise_ai"
    )
