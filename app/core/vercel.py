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
        trusted_hosts=",".join(dict.fromkeys(host.strip() for host in hosts if host.strip())),
    )
