"""Small injectable retry, failure-classification, and timeout primitives."""

import random
import threading
from collections.abc import Callable
from queue import Empty, Queue

from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

from app.runtime.models import FailureCategory, RetryPolicy


class OperationTimeoutError(TimeoutError):
    """A bounded operation exceeded its configured time budget."""


def classify_failure(exc: Exception) -> FailureCategory:
    """Classify known transient OpenAI conditions without exposing exception text."""
    if isinstance(exc, APITimeoutError | OperationTimeoutError):
        return FailureCategory.TIMEOUT
    if isinstance(exc, RateLimitError | APIConnectionError | InternalServerError):
        return FailureCategory.TRANSIENT
    if isinstance(exc, ValueError | TypeError):
        return FailureCategory.VALIDATION
    return FailureCategory.PERMANENT


def run_with_retry[ResultT](
    operation: Callable[[], ResultT],
    *,
    policy: RetryPolicy,
    sleeper: Callable[[float], None],
    random_value: Callable[[], float] = random.random,
    on_retry: Callable[[int, FailureCategory], None] | None = None,
) -> ResultT:
    """Retry only transient/timeout failures with bounded exponential backoff."""
    for attempt in range(policy.max_retries + 1):
        try:
            return operation()
        except Exception as exc:
            category = classify_failure(exc)
            if category not in {FailureCategory.TRANSIENT, FailureCategory.TIMEOUT}:
                raise
            if attempt >= policy.max_retries:
                raise
            if on_retry is not None:
                on_retry(attempt + 1, category)
            base = min(policy.max_delay_ms, policy.base_delay_ms * (2**attempt))
            jitter = base * policy.jitter_ratio * random_value()
            sleeper((base + jitter) / 1_000)
    raise RuntimeError("bounded retry loop ended unexpectedly")


def run_with_timeout[ResultT](
    operation: Callable[[], ResultT],
    *,
    timeout_seconds: float,
) -> ResultT:
    """Bound a read-only synchronous operation using an isolated daemon worker."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    outcomes: Queue[tuple[bool, object]] = Queue(maxsize=1)

    def invoke() -> None:
        try:
            outcomes.put((True, operation()))
        except BaseException as exc:
            outcomes.put((False, exc))

    worker = threading.Thread(target=invoke, daemon=True, name="bounded-runtime-operation")
    worker.start()
    try:
        succeeded, value = outcomes.get(timeout=timeout_seconds)
    except Empty as exc:
        raise OperationTimeoutError from exc
    if succeeded:
        return value  # type: ignore[return-value]
    raise value  # type: ignore[misc]
