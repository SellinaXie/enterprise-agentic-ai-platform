"""Request correlation context shared by logs and execution metadata."""

from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the current bounded request identifier, when inside an HTTP request."""
    return _request_id.get()


def set_request_id(request_id: str) -> Token[str | None]:
    """Bind a request identifier for the current async context."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the prior request context after a response completes."""
    _request_id.reset(token)
