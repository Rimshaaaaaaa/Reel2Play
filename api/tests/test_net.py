from __future__ import annotations

import httpx
import pytest

from reel2play.net import ExternalServiceError, is_retryable, raise_for_status, with_retries


def test_retries_transient_errors_then_succeeds() -> None:
    attempts: list[int] = []
    delays: list[float] = []

    def flaky() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise ExternalServiceError("svc", "busy", status=503)
        return "ok"

    assert with_retries(flaky, attempts=3, base_delay=0.1, sleep=delays.append) == "ok"
    assert delays == [0.1, 0.2]


def test_gives_up_after_last_attempt() -> None:
    def always() -> None:
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        with_retries(always, attempts=2, sleep=lambda _: None)


def test_does_not_retry_client_errors() -> None:
    calls: list[int] = []

    def bad() -> None:
        calls.append(1)
        raise ExternalServiceError("svc", "bad request", status=400)

    with pytest.raises(ExternalServiceError):
        with_retries(bad, attempts=3, sleep=lambda _: None)
    assert calls == [1]


def test_retryable_classification() -> None:
    assert is_retryable(ExternalServiceError("s", "x", status=429))
    assert is_retryable(ExternalServiceError("s", "x"))
    assert not is_retryable(ExternalServiceError("s", "x", status=401))
    assert is_retryable(httpx.ReadTimeout("slow"))
    assert not is_retryable(ValueError("nope"))


def test_raise_for_status_names_the_service() -> None:
    raise_for_status("svc", httpx.Response(200))
    with pytest.raises(ExternalServiceError, match="svc: HTTP 502: gateway") as info:
        raise_for_status("svc", httpx.Response(502, text="gateway\nerror"))
    assert info.value.status == 502
