"""Bounded retry, timeout, and structured failure classification tests."""

from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError

from app.runtime.models import FailureCategory, RetryPolicy
from app.runtime.resilience import (
    OperationTimeoutError,
    classify_failure,
    run_with_retry,
    run_with_timeout,
)


def _connection_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1"))


def test_transient_failure_retries_with_bounded_backoff() -> None:
    operation = Mock(side_effect=[_connection_error(), _connection_error(), "ok"])
    delays: list[float] = []
    retries: list[tuple[int, FailureCategory]] = []

    result = run_with_retry(
        operation,
        policy=RetryPolicy(max_retries=2, base_delay_ms=100, jitter_ratio=0),
        sleeper=delays.append,
        on_retry=lambda attempt, category: retries.append((attempt, category)),
    )

    assert result == "ok"
    assert operation.call_count == 3
    assert delays == [0.1, 0.2]
    assert retries == [(1, FailureCategory.TRANSIENT), (2, FailureCategory.TRANSIENT)]


def test_permanent_failure_is_not_retried() -> None:
    operation = Mock(side_effect=RuntimeError("permanent"))

    with pytest.raises(RuntimeError):
        run_with_retry(
            operation,
            policy=RetryPolicy(max_retries=2),
            sleeper=Mock(),
        )

    operation.assert_called_once()


def test_retry_exhaustion_is_bounded() -> None:
    operation = Mock(side_effect=_connection_error())

    with pytest.raises(APIConnectionError):
        run_with_retry(
            operation,
            policy=RetryPolicy(max_retries=2, base_delay_ms=0, jitter_ratio=0),
            sleeper=Mock(),
        )

    assert operation.call_count == 3


@pytest.mark.parametrize(
    "operation_name",
    ["model", "embedding", "tool", "graph_extraction"],
)
def test_external_operation_timeout_is_structured_without_real_wait(
    operation_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    del operation_name

    class ImmediateTimeoutQueue:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def get(self, *, timeout: float) -> object:
            del timeout
            from queue import Empty

            raise Empty

        def put(self, value: object) -> None:
            del value

    monkeypatch.setattr("app.runtime.resilience.Queue", ImmediateTimeoutQueue)

    with pytest.raises(OperationTimeoutError) as caught:
        run_with_timeout(lambda: "never observed", timeout_seconds=1)

    assert str(caught.value) == ""
    assert classify_failure(caught.value) == FailureCategory.TIMEOUT
