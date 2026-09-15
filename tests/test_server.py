"""Hosting entry-point tests."""

import pytest

from app.server import get_port


def test_server_port_defaults_to_container_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PORT", raising=False)
    assert get_port() == 8000


def test_server_port_uses_host_assignment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "10000")
    assert get_port() == 10000


@pytest.mark.parametrize("value", ["invalid", "0", "65536"])
def test_server_port_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("PORT", value)
    with pytest.raises(RuntimeError, match="PORT must"):
        get_port()
