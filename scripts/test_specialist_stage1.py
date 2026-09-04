"""Deterministic tests for Specialist Roles Stage 1 integration.

No OpenRouter/network calls are made. Model calls and API pipeline stages are
monkeypatched with local fakes.
"""

from __future__ import annotations

import asyncio

import backend.council as council
import backend.main as main_api
from backend.config import COUNCIL_MODELS
from backend.conversation_context import (
    build_contextual_query,
    build_conversation_context,
)
from backend.specialists import plan_specialist_seats


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def test_stage1_uses_three_distinct_specialist_prompts() -> None:
    original_query_model = council.query_model
    calls = []

    async def fake_query_model(model, messages, *args, **kwargs):
        calls.append(
            {
                "model": model,
                "messages": messages,
            }
        )
        return {
            "content": f"answer from {model}",
            "model": model,
            "requested_model": model,
        }

    council.query_model = fake_query_model

    raw_query = (
        "How should I optimise the SEO of this Wix product page?"
    )
    conversation_context = (
        "[User message]\nEarlier we discussed AliExpress suppliers "
        "and shipping."
    )
    contextual_query = build_contextual_query(
        raw_query,
        conversation_context,
    )
    knowledge_context = (
        "[Knowledge source: memory/entities/brand-rovebury.md]\n"
        "ROVEBURY fixture knowledge."
    )

    try:
        results = await council.stage1_collect_responses(
            contextual_query,
            knowledge_context,
            routing_query=raw_query,
            conversation_context=conversation_context,
        )
    finally:
        council.query_model = original_query_model

    routing, expected_seats = plan_specialist_seats(
        raw_query,
        COUNCIL_MODELS,
        conversation_context,
    )

    require(
        routing["selected_roles"] == [
            "seo_strategist",
            "wix_specialist",
            "ecommerce_cro",
        ],
        f"Unexpected specialist route: {routing!r}",
    )
    require(
        len(calls) == len(COUNCIL_MODELS) == 3,
        f"Stage 1 changed the normal model call count: {len(calls)}.",
    )
    require(
        len(results) == 3,
        f"Expected 3 successful Stage 1 results, got {len(results)}.",
    )

    for call, result, seat in zip(
        calls,
        results,
        expected_seats,
    ):
        require(
            call["model"] == seat["model"],
            f"Wrong model for specialist seat: {call!r} vs {seat!r}",
        )
        require(
            len(call["messages"]) == 1,
            f"Specialist seat should receive one user message: {call!r}",
        )

        prompt = call["messages"][0]["content"]

        require(
            seat["role_name"] in prompt,
            f"Specialist role missing from prompt: {seat!r}",
        )
        require(
            knowledge_context in prompt,
            f"Knowledge context missing from specialist prompt: {seat!r}",
        )
        require(
            contextual_query in prompt,
            f"Contextual Council query missing from prompt: {seat!r}",
        )
        require(
            result["model"] == seat["model"],
            f"Stage 1 lost configured model identity: {result!r}",
        )
        require(
            result["seat"] == seat["seat"],
            f"Stage 1 lost seat identity: {result!r}",
        )
        require(
            result["role_id"] == seat["role_id"],
            f"Stage 1 lost role_id: {result!r}",
        )
        require(
            result["role_name"] == seat["role_name"],
            f"Stage 1 lost role_name: {result!r}",
        )


async def test_failed_seat_does_not_create_replacement_calls() -> None:
    original_query_model = council.query_model
    calls = []

    async def fake_query_model(model, messages, *args, **kwargs):
        calls.append(model)
        if model == COUNCIL_MODELS[-1]:
            return None
        return {
            "content": f"answer from {model}",
            "model": model,
        }

    council.query_model = fake_query_model

    try:
        results = await council.stage1_collect_responses(
            "Review SEO, Wix and product-page conversion.",
            "",
            routing_query=(
                "Review SEO, Wix and product-page conversion."
            ),
        )
    finally:
        council.query_model = original_query_model

    require(
        calls == COUNCIL_MODELS,
        f"Stage 1 added or reordered model calls: {calls!r}",
    )
    require(
        len(results) == 2,
        f"One failed seat should degrade to 2 responses: {results!r}",
    )


async def test_run_full_council_preserves_raw_query_boundaries() -> None:
    originals = {
        "get_knowledge_context": council.get_knowledge_context,
        "stage1_collect_responses": council.stage1_collect_responses,
        "stage2_collect_rankings": council.stage2_collect_rankings,
        "calculate_aggregate_rankings": council.calculate_aggregate_rankings,
        "stage3_synthesize_final": council.stage3_synthesize_final,
    }
    captured = {}

    raw_query = (
        "How should I optimise SEO on the Wix product page?"
    )
    conversation_context = (
        "[User message]\nEarlier we discussed AliExpress suppliers."
    )
    expected_council_query = build_contextual_query(
        raw_query,
        conversation_context,
    )

    def fake_get_knowledge_context(query):
        captured["knowledge_query"] = query
        return "PRE_RETRIEVED_KNOWLEDGE"

    async def fake_stage1(
        user_query,
        knowledge_context=None,
        *,
        routing_query=None,
        conversation_context="",
    ):
        captured["stage1_user_query"] = user_query
        captured["stage1_knowledge"] = knowledge_context
        captured["stage1_routing_query"] = routing_query
        captured["stage1_conversation_context"] = conversation_context
        return [
            {
                "model": "model/a",
                "seat": "A",
                "role_id": "seo_strategist",
                "role_name": "SEO Strategist",
                "response": "answer",
            }
        ]

    async def fake_stage2(user_query, stage1_results):
        return [], {"Response A": "model/a"}

    def fake_aggregate(stage2_results, label_to_model):
        return []

    async def fake_stage3(
        user_query,
        stage1_results,
        stage2_results,
        knowledge_context=None,
    ):
        return {
            "model": "chairman/model",
            "response": "final",
            "primary_model": "chairman/model",
            "route_model": "chairman/model",
            "fallback_used": False,
        }

    council.get_knowledge_context = fake_get_knowledge_context
    council.stage1_collect_responses = fake_stage1
    council.stage2_collect_rankings = fake_stage2
    council.calculate_aggregate_rankings = fake_aggregate
    council.stage3_synthesize_final = fake_stage3

    try:
        await council.run_full_council(
            raw_query,
            conversation_context,
        )
    finally:
        for name, value in originals.items():
            setattr(council, name, value)

    require(
        captured["knowledge_query"] == raw_query,
        "Knowledge retrieval did not receive the raw current user query.",
    )
    require(
        captured["stage1_routing_query"] == raw_query,
        "Specialist router did not receive the raw current user query.",
    )
    require(
        captured["stage1_conversation_context"]
        == conversation_context,
        "Specialist router did not receive conversation context separately.",
    )
    require(
        captured["stage1_user_query"] == expected_council_query,
        "Stage 1 model prompt did not receive the contextual Council query.",
    )
    require(
        captured["stage1_knowledge"] == "PRE_RETRIEVED_KNOWLEDGE",
        "Stage 1 did not reuse pre-retrieved knowledge.",
    )


async def test_streaming_preserves_raw_query_boundaries() -> None:
    storage = main_api.storage

    originals = {
        "get_conversation": storage.get_conversation,
        "add_user_message": storage.add_user_message,
        "add_assistant_message": storage.add_assistant_message,
        "get_knowledge_context": main_api.get_knowledge_context,
        "stage1_collect_responses": main_api.stage1_collect_responses,
        "stage2_collect_rankings": main_api.stage2_collect_rankings,
        "calculate_aggregate_rankings": (
            main_api.calculate_aggregate_rankings
        ),
        "stage3_synthesize_final": main_api.stage3_synthesize_final,
    }

    captured = {}
    raw_query = "How should the Wix SEO product page be improved?"
    previous_messages = [
        {
            "role": "user",
            "content": (
                "Earlier we discussed AliExpress suppliers and shipping."
            ),
        }
    ]
    expected_context = build_conversation_context(
        previous_messages
    )
    expected_council_query = build_contextual_query(
        raw_query,
        expected_context,
    )

    def fake_get_conversation(conversation_id):
        return {
            "id": conversation_id,
            "title": "Existing Conversation",
            "created_at": "2026-09-04T00:00:00",
            "messages": previous_messages,
        }

    def no_op(*args, **kwargs):
        return None

    def fake_get_knowledge_context(query):
        captured["knowledge_query"] = query
        return "STREAM_KNOWLEDGE"

    async def fake_stage1(
        user_query,
        knowledge_context=None,
        *,
        routing_query=None,
        conversation_context="",
    ):
        captured["stage1_user_query"] = user_query
        captured["stage1_knowledge"] = knowledge_context
        captured["stage1_routing_query"] = routing_query
        captured["stage1_conversation_context"] = conversation_context
        return [
            {
                "model": "model/a",
                "seat": "A",
                "role_id": "seo_strategist",
                "role_name": "SEO Strategist",
                "response": "answer",
            }
        ]

    async def fake_stage2(user_query, stage1_results):
        return [], {"Response A": "model/a"}

    def fake_aggregate(stage2_results, label_to_model):
        return []

    async def fake_stage3(
        user_query,
        stage1_results,
        stage2_results,
        knowledge_context=None,
    ):
        return {
            "model": "chairman/model",
            "response": "final",
            "primary_model": "chairman/model",
            "route_model": "chairman/model",
            "fallback_used": False,
        }

    storage.get_conversation = fake_get_conversation
    storage.add_user_message = no_op
    storage.add_assistant_message = no_op
    main_api.get_knowledge_context = fake_get_knowledge_context
    main_api.stage1_collect_responses = fake_stage1
    main_api.stage2_collect_rankings = fake_stage2
    main_api.calculate_aggregate_rankings = fake_aggregate
    main_api.stage3_synthesize_final = fake_stage3

    try:
        response = await main_api.send_message_stream(
            "test-conversation",
            main_api.SendMessageRequest(content=raw_query),
        )

        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
    finally:
        storage.get_conversation = originals["get_conversation"]
        storage.add_user_message = originals["add_user_message"]
        storage.add_assistant_message = originals[
            "add_assistant_message"
        ]
        main_api.get_knowledge_context = originals[
            "get_knowledge_context"
        ]
        main_api.stage1_collect_responses = originals[
            "stage1_collect_responses"
        ]
        main_api.stage2_collect_rankings = originals[
            "stage2_collect_rankings"
        ]
        main_api.calculate_aggregate_rankings = originals[
            "calculate_aggregate_rankings"
        ]
        main_api.stage3_synthesize_final = originals[
            "stage3_synthesize_final"
        ]

    stream_text = "".join(
        chunk.decode("utf-8")
        if isinstance(chunk, bytes)
        else chunk
        for chunk in chunks
    )

    require(
        '"type": "error"' not in stream_text,
        f"Deterministic streaming test emitted an error: {stream_text}",
    )
    require(
        captured["knowledge_query"] == raw_query,
        "Streaming knowledge retrieval did not use raw current query.",
    )
    require(
        captured["stage1_routing_query"] == raw_query,
        "Streaming specialist routing did not use raw current query.",
    )
    require(
        captured["stage1_conversation_context"] == expected_context,
        "Streaming router did not receive conversation context separately.",
    )
    require(
        captured["stage1_user_query"] == expected_council_query,
        "Streaming Stage 1 did not receive contextual Council query.",
    )
    require(
        captured["stage1_knowledge"] == "STREAM_KNOWLEDGE",
        "Streaming Stage 1 did not reuse pre-retrieved knowledge.",
    )


async def main() -> None:
    await test_stage1_uses_three_distinct_specialist_prompts()
    print("PASS  Stage 1 uses three distinct specialist prompts")

    await test_failed_seat_does_not_create_replacement_calls()
    print("PASS  failed specialist seat adds no replacement calls")

    await test_run_full_council_preserves_raw_query_boundaries()
    print("PASS  non-stream Council preserves raw routing/retrieval boundaries")

    await test_streaming_preserves_raw_query_boundaries()
    print("PASS  streaming Council preserves raw routing/retrieval boundaries")

    print("\nSpecialist Stage 1 integration tests PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
