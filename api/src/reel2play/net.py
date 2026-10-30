"""Shared helpers for external calls: timeouts, retries with backoff, clear errors."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import httpx

log = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class ExternalServiceError(RuntimeError):
    """A call to an outside service failed; the message says which one and why."""

    def __init__(self, service: str, detail: str, *, status: int | None = None) -> None:
        super().__init__(f"{service}: {detail}")
        self.service = service
        self.detail = detail
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.status is None or self.status in RETRYABLE_STATUS


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ExternalServiceError):
        return exc.retryable
    return isinstance(exc, httpx.TransportError)


def with_retries[T](
    call: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_if: Callable[[BaseException], bool] = is_retryable,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run ``call``; retry with backoff while ``retry_if`` says the error is transient."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:
            if attempt == attempts or not retry_if(exc):
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            log.warning(
                "retrying after %s (attempt %d/%d): %s", type(exc).__name__, attempt, attempts, exc
            )
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


def raise_for_status(service: str, response: httpx.Response) -> None:
    if response.is_success:
        return
    body = response.text[:300].replace("\n", " ")
    raise ExternalServiceError(
        service, f"HTTP {response.status_code}: {body}", status=response.status_code
    )


def make_client(
    timeout: httpx.Timeout = DEFAULT_TIMEOUT, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    return httpx.Client(timeout=timeout, transport=transport, follow_redirects=False)
