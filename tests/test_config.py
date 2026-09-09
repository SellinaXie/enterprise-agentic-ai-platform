"""Configuration secrecy tests."""

from app.core.config import Settings


def test_database_url_is_redacted_from_settings_representation() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg://user:private-password@localhost/enterprise_ai",
    )

    assert "private-password" not in repr(settings)
    assert "**********" in repr(settings)
