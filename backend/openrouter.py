"""OpenRouter API client with bounded retry/backoff and fallback helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import httpx

from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL


RETRYABLE_STATUS_CODES = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_SECONDS = 1.0
DEFAULT_MAX_BACKOFF_SECONDS = 8.0


def _is_retryable_error(exc: Exception) -> bool:
    """Return True only for transient HTTP or transport failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        return response.status_code in RETRYABLE_STATUS_CODES

    return isinstance(exc, httpx.RequestError)


def _retry_after_seconds(
    exc: Exception,
    *,
    now: Optional[datetime] = None,
) -> Optional[float]:
    """Parse Retry-After as seconds or an HTTP date when available."""
    if not isinstance(exc, httpx.HTTPStatusError):
        return None

    raw_value = exc.response.headers.get("Retry-After")
    if not raw_value:
        return None

    try:
        seconds = float(raw_value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw_value)
        except (TypeError, ValueError, OverflowError):
            return None

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)

        current = now or datetime.now(timezone.utc)
        seconds = (retry_at - current).total_seconds()

    return max(0.0, seconds)


def _retry_delay_seconds(
    attempt: int,
    exc: Exception,
    *,
    backoff_base: float,
    max_backoff: float,
) -> float:
    """Calculate bounded exponential backoff, preferring Retry-After."""
    retry_after = _retry_after_seconds(exc)

    if retry_after is not None:
        return min(retry_after, max_backoff)

    exponential = backoff_base * (2 ** max(0, attempt - 1))
    return min(exponential, max_backoff)


def _error_label(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"

    if isinstance(exc, httpx.TimeoutException):
        return "timeout"

    if isinstance(exc, httpx.RequestError):
        return exc.__class__.__name__

    return exc.__class__.__name__


async def _send_request(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float,
) -> Dict[str, Any]:
    """Send one OpenRouter request. Retry policy lives in query_model()."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        data = response.json()
        message = data["choices"][0]["message"]

        return {
            "content": message.get("content"),
            "reasoning_details": message.get("reasoning_details"),
            "model": data.get("model", model),
            "requested_model": model,
        }


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
    max_backoff: float = DEFAULT_MAX_BACKOFF_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Query one model with bounded retries for transient failures.

    Permanent client errors such as 400/401/403/404 are not retried.
    Transient failures such as 429, selected 5xx responses, timeouts, and
    transport errors use bounded exponential backoff. Retry-After is honoured
    when present, capped by max_backoff.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    if backoff_base < 0 or max_backoff < 0:
        raise ValueError("backoff values must be non-negative")

    for attempt in range(1, max_attempts + 1):
        try:
            return await _send_request(
                model,
                messages,
                timeout,
            )
        except Exception as exc:
            retryable = _is_retryable_error(exc)
            is_last_attempt = attempt >= max_attempts

            if retryable and not is_last_attempt:
                delay = _retry_delay_seconds(
                    attempt,
                    exc,
                    backoff_base=backoff_base,
                    max_backoff=max_backoff,
                )

                print(
                    f"Transient OpenRouter error for {model}: "
                    f"{_error_label(exc)}. "
                    f"Retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{max_attempts})."
                )

                await asyncio.sleep(delay)
                continue

            print(
                f"Error querying model {model} after "
                f"{attempt} attempt(s): {_error_label(exc)}"
            )
            return None

    return None


async def query_model_with_fallback(
    models: List[str],
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
    max_backoff: float = DEFAULT_MAX_BACKOFF_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Try candidate models sequentially after each candidate exhausts retries.

    Duplicate model IDs are ignored while preserving order. The returned
    response records the primary requested model, the route that succeeded,
    and whether fallback was required.
    """
    candidates = list(dict.fromkeys(models))

    if not candidates:
        return None

    primary_model = candidates[0]

    for index, candidate in enumerate(candidates):
        if index > 0:
            print(
                f"Trying fallback model {candidate} "
                f"for primary {primary_model}."
            )

        response = await query_model(
            candidate,
            messages,
            timeout=timeout,
            max_attempts=max_attempts,
            backoff_base=backoff_base,
            max_backoff=max_backoff,
        )

        if response is None:
            continue

        result = dict(response)
        result["primary_model"] = primary_model
        result["route_model"] = candidate
        result["fallback_used"] = candidate != primary_model

        return result

    print(
        "All OpenRouter fallback candidates failed: "
        + ", ".join(candidates)
    )
    return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query multiple council models in parallel.

    Each individual model uses query_model(), so transient failures receive
    bounded retry/backoff without changing the existing return shape.
    """
    tasks = [
        query_model(model, messages)
        for model in models
    ]

    responses = await asyncio.gather(*tasks)

    return {
        model: response
        for model, response in zip(models, responses)
    }
