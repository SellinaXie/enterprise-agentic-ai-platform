"""Fail a backend build on invalid configuration without printing secret inputs."""

import os

from pydantic import ValidationError

from app.core.vercel import vercel_settings


def main() -> int:
    try:
        vercel_settings()
    except ValidationError as exc:
        print("Vercel backend configuration is not ready:")
        for key in (
            "DATABASE_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "AUTH_JWT_VERIFICATION_KEY", "AUTH_JWKS_URL",
            "AUTH_JWT_ISSUER", "AUTH_JWT_AUDIENCE",
        ):
            value = os.environ.get(key)
            state = "missing" if value is None else "empty" if not value.strip() else "set"
            print(f"- {key}: {state}")
        for error in exc.errors(include_input=False, include_url=False):
            location = ".".join(str(part) for part in error["loc"]) or "production settings"
            print(f"- {location}: {error['msg']}")
        return 1
    print("Vercel backend production configuration validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
