"""Deterministic tests for Chairman and title fallback integration."""

from __future__ import annotations

import asyncio

import backend.council as council
from backend.config import (
    CHAIRMAN_MODEL,
    CHAIRMAN_MODELS,
    COUNCIL_MODELS,
    TITLE_MODELS,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def test_candidate_configuration() -> None:
    expected_chairman = list(
        dict.fromkeys(
            [
                CHAIRMAN_MODEL,
                *COUNCIL_MODELS,
            ]
        )
    )

    expected_title = list(
        dict.fromkeys(
            [
                CHAIRMAN_MODEL,
                "openrouter/free",
            ]
        )
    )

    require(
        CHAIRMAN_MODELS == expected_chairman,
        f"Unexpected Chairman candidates: {CHAIRMAN_MODELS!r}",
    )
    require(
        TITLE_MODELS == expected_title,
        f"Unexpected title candidates: {TITLE_MODELS!r}",
    )


async def test_stage3_records_actual_fallback_route() -> None:
    original = council.query_model_with_fallback
    calls = []

    async def fake_query_model_with_fallback(
        models,
        messages,
        timeout=120.0,
        **kwargs,
    ):
        calls.append(
            {
                "models": list(models),
                "timeout": timeout,
                "kwargs": dict(kwargs),
            }
        )

        return {
            "content": "Fallback synthesis",
            "model": "provider/actual-fallback-model",
            "requested_model": "openrouter/free",
            "primary_model": CHAIRMAN_MODEL,
            "route_model": "openrouter/free",
            "fallback_used": True,
        }

    council.query_model_with_fallback = fake_query_model_with_fallback

    try:
        result = await council.stage3_synthesize_final(
            "What should ROVEBURY do?",
            [
                {
                    "model": "member/a",
                    "response": "Candidate answer",
                }
            ],
            [],
            "",
        )
    finally:
        council.query_model_with_fallback = original

    require(len(calls) == 1, "Stage 3 should make one fallback-helper call.")
    require(
        calls[0]["models"] == CHAIRMAN_MODELS,
        "Stage 3 did not use CHAIRMAN_MODELS.",
    )
    require(
        result["model"] == "provider/actual-fallback-model",
        f"Stage 3 lost actual model identity: {result!r}",
    )
    require(
        result["primary_model"] == CHAIRMAN_MODEL,
        f"Stage 3 lost primary Chairman identity: {result!r}",
    )
    require(
        result["route_model"] == "openrouter/free",
        f"Stage 3 lost fallback route identity: {result!r}",
    )
    require(
        result["fallback_used"] is True,
        f"Stage 3 should report fallback_used=True: {result!r}",
    )


async def test_title_uses_lightweight_fallback() -> None:
    original = council.query_model_with_fallback
    calls = []

    async def fake_query_model_with_fallback(
        models,
        messages,
        timeout=120.0,
        **kwargs,
    ):
        calls.append(
            {
                "models": list(models),
                "timeout": timeout,
                "kwargs": dict(kwargs),
            }
        )

        return {
            "content": '"ROVEBURY Test Title"',
            "model": "provider/title-model",
            "primary_model": CHAIRMAN_MODEL,
            "route_model": "openrouter/free",
            "fallback_used": True,
        }

    council.query_model_with_fallback = fake_query_model_with_fallback

    try:
        title = await council.generate_conversation_title(
            "A test question about ROVEBURY"
        )
    finally:
        council.query_model_with_fallback = original

    require(len(calls) == 1, "Title generation should make one helper call.")
    require(
        calls[0]["models"] == TITLE_MODELS,
        "Title generation did not use TITLE_MODELS.",
    )
    require(
        calls[0]["timeout"] == 30.0,
        f"Unexpected title timeout: {calls[0]['timeout']}",
    )
    require(
        calls[0]["kwargs"].get("max_attempts") == 1,
        "Title generation should use one attempt per candidate.",
    )
    require(
        title == "ROVEBURY Test Title",
        f"Unexpected normalized title: {title!r}",
    )


async def test_graceful_failure_defaults() -> None:
    original = council.query_model_with_fallback

    async def always_fail(*args, **kwargs):
        return None

    council.query_model_with_fallback = always_fail

    try:
        stage3 = await council.stage3_synthesize_final(
            "test",
            [
                {
                    "model": "member/a",
                    "response": "answer",
                }
            ],
            [],
            "",
        )
        title = await council.generate_conversation_title("test")
    finally:
        council.query_model_with_fallback = original

    require(
        stage3["response"] == "Error: Unable to generate final synthesis.",
        f"Unexpected Stage 3 failure result: {stage3!r}",
    )
    require(
        stage3["route_model"] is None,
        f"Failed Stage 3 should not invent a route: {stage3!r}",
    )
    require(
        stage3["fallback_used"] is False,
        f"Failed Stage 3 should not claim successful fallback: {stage3!r}",
    )
    require(
        title == "New Conversation",
        f"Unexpected failed-title default: {title!r}",
    )


async def main() -> None:
    await test_candidate_configuration()
    print("PASS  Chairman/title candidate configuration")

    await test_stage3_records_actual_fallback_route()
    print("PASS  Stage 3 records actual fallback route")

    await test_title_uses_lightweight_fallback()
    print("PASS  title uses lightweight one-attempt fallback")

    await test_graceful_failure_defaults()
    print("PASS  Chairman/title failures keep graceful defaults")

    print("\nChairman + title fallback tests PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
