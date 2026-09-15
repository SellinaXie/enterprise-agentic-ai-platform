"""Create the two synthetic V8D portfolio scenarios in a prepared local database."""

from app.core.config import get_settings
from app.db.session import get_database_url, get_session_factory
from app.demo.seed import seed_demo_scenarios


def main() -> None:
    settings = get_settings()
    if settings.environment not in {"local", "development", "test"}:
        raise RuntimeError("Synthetic demo seeding is disabled outside local/development/test")
    factory = get_session_factory(
        get_database_url(settings), settings.database_connect_timeout_seconds
    )
    with factory() as session:
        seeded = seed_demo_scenarios(session)
    for item in seeded:
        print(f"{item.scenario}: {item.assessment_id} ({item.status.value})")


if __name__ == "__main__":
    main()
