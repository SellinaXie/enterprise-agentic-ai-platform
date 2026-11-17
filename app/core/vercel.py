"""Production settings for the Vercel backend service."""

import os

from app.core.config import Settings


def vercel_settings() -> Settings:
    """Keep the production identity boundary and allow this deployment's exact host."""
    hosts = os.environ.get("TRUSTED_HOSTS", "localhost,127.0.0.1").split(",")
    for key in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        host = os.environ.get(key, "").strip()
        if host and "/" not in host and ":" not in host:
            hosts.append(host)
    return Settings(
        _env_ignore_empty=True,
        APP_ENV="production",
        AUTH_ENABLED=True,
        APP_DEBUG=False,
        LOG_EXCEPTION_TRACEBACKS=False,
        # Vercel Secret names cannot be changed after creation. Accept the
        # owner's existing name without reading the value back through the API.
        openai_api_key=(
            os.environ.get("OPENAI_API_KEY", "").strip()
            or os.environ.get("OpenAI", "").strip()  # noqa: SIM112
            or None
        ),
        trusted_hosts=",".join(dict.fromkeys(host.strip() for host in hosts if host.strip())),
    )
