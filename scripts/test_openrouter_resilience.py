"""Deterministic tests for OpenRouter retry/backoff/fallback behavior."""

from __future__ import annotations

import asyncio

import httpx

import backend.openrouter as openrouter


MESSAGES = [
    {
        "role": "user",
        "content": "test",
    }
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def status_error(
    status_code: int,
    *,
    retry_after: str | None = None,
) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
    )

    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after

    response = httpx.Response(
        status_code,
        request=request,
        headers=headers,
    )

    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


async def test_429_retries_then_succeeds() -> None:
    original_send = openrouter._send_request
    original_sleep = openrouter.asyncio.sleep

    calls = 0
    sleeps: list[float] = []

    async def fake_send(model, messages, timeout):
        nonlocal calls
        calls += 1

        if calls == 1:
            raise status_error(
                429,
                retry_after="0",
            )

        return {
            "content": "ok",
            "model": model,
            "requested_model": model,
        }

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    openrouter._send_request = fake_send
    openrouter.asyncio.sleep = fake_sleep

    try:
        result = await openrouter.query_model(
            "test/model",
            MESSAGES,
            max_attempts=3,
        )
    finally:
        openrouter._send_request = original_send
        openrouter.asyncio.sleep = original_sleep

    require(result is not None, "429 retry should eventually succeed.")
    require(calls == 2, f"Expected 2 attempts, got {calls}.")
    require(sleeps == [0.0], f"Unexpected sleeps: {sleeps!r}.")


async def test_permanent_401_is_not_retried() -> None:
    original_send = openrouter._send_request
    original_sleep = openrouter.asyncio.sleep

    calls = 0
    sleeps: list[float] = []

    async def fake_send(model, messages, timeout):
        nonlocal calls
        calls += 1
        raise status_error(401)

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    openrouter._send_request = fake_send
    openrouter.asyncio.sleep = fake_sleep

    try:
        result = await openrouter.query_model(
            "test/model",
            MESSAGES,
            max_attempts=3,
        )
    finally:
        openrouter._send_request = original_send
        openrouter.asyncio.sleep = original_sleep

    require(result is None, "401 should fail without a response.")
    require(calls == 1, f"401 was retried unexpectedly: {calls} calls.")
    require(not sleeps, f"401 should not sleep: {sleeps!r}.")


async def test_transport_error_uses_exponential_backoff() -> None:
    original_send = openrouter._send_request
    original_sleep = openrouter.asyncio.sleep

    calls = 0
    sleeps: list[float] = []

    async def fake_send(model, messages, timeout):
        nonlocal calls
        calls += 1

        if calls < 3:
            request = httpx.Request(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
            )
            raise httpx.ConnectError(
                "temporary connection failure",
                request=request,
            )

        return {
            "content": "recovered",
            "model": model,
            "requested_model": model,
        }

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    openrouter._send_request = fake_send
    openrouter.asyncio.sleep = fake_sleep

    try:
        result = await openrouter.query_model(
            "test/model",
            MESSAGES,
            max_attempts=3,
            backoff_base=1.0,
            max_backoff=8.0,
        )
    finally:
        openrouter._send_request = original_send
        openrouter.asyncio.sleep = original_sleep

    require(result is not None, "Transport retry should recover.")
    require(calls == 3, f"Expected 3 attempts, got {calls}.")
    require(
        sleeps == [1.0, 2.0],
        f"Unexpected exponential backoff: {sleeps!r}.",
    )


async def test_fallback_moves_to_next_candidate() -> None:
    original_query_model = openrouter.query_model

    calls: list[str] = []

    async def fake_query_model(
        model,
        messages,
        timeout=120.0,
        **kwargs,
    ):
        calls.append(model)

        if model == "primary/model":
            return None

        return {
            "content": "fallback response",
            "model": "actual/provider-model",
            "requested_model": model,
        }

    openrouter.query_model = fake_query_model

    try:
        result = await openrouter.query_model_with_fallback(
            [
                "primary/model",
                "fallback/model",
                "fallback/model",
            ],
            MESSAGES,
        )
    finally:
        openrouter.query_model = original_query_model

    require(
        calls == ["primary/model", "fallback/model"],
        f"Fallback order/deduplication failed: {calls!r}.",
    )
    require(result is not None, "Fallback should return a response.")
    require(
        result.get("primary_model") == "primary/model",
        "Primary model metadata is incorrect.",
    )
    require(
        result.get("route_model") == "fallback/model",
        "Fallback route metadata is incorrect.",
    )
    require(
        result.get("fallback_used") is True,
        "Fallback metadata should report fallback_used=True.",
    )


async def test_retry_after_is_capped() -> None:
    exc = status_error(
        429,
        retry_after="60",
    )

    delay = openrouter._retry_delay_seconds(
        1,
        exc,
        backoff_base=1.0,
        max_backoff=8.0,
    )

    require(
        delay == 8.0,
        f"Retry-After should be capped at 8.0s, got {delay}.",
    )


async def main() -> None:
    await test_429_retries_then_succeeds()
    print("PASS  429 retries then succeeds")

    await test_permanent_401_is_not_retried()
    print("PASS  permanent 401 is not retried")

    await test_transport_error_uses_exponential_backoff()
    print("PASS  transport errors use exponential backoff")

    await test_fallback_moves_to_next_candidate()
    print("PASS  fallback moves to the next distinct candidate")

    await test_retry_after_is_capped()
    print("PASS  Retry-After is bounded by the configured cap")

    print("\nOpenRouter resilience tests PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
