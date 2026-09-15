"""Container entry point that honors the hosting platform's assigned port."""

import os

import uvicorn


def get_port() -> int:
    """Return a validated TCP port, defaulting to the local container port."""
    raw_port = os.getenv("PORT", "8000")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise RuntimeError("PORT must be an integer") from exc
    if not 1 <= port <= 65_535:
        raise RuntimeError("PORT must be between 1 and 65535")
    return port


def main() -> None:
    """Start the production ASGI server."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=get_port(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
