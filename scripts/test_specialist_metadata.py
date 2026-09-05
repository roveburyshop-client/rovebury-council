# Deterministic tests for Phase 5B specialist metadata integration.
from __future__ import annotations

import asyncio
import json

import backend.council as council
import backend.main as main_api
from backend.config import COUNCIL_MODELS
from backend.conversation_context import build_conversation_context


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def empty_access_metadata() -> dict:
    return {
        "router_version": "access-rules-v1",
        "mode": "none",
        "required": False,
        "blocked_by_user": False,
        "used_conversation_context": False,
        "requested_capabilities": [],
        "reason_codes": [],
        "sources_used": [],
        "failures": [],
        "missing_capabilities": [],
        "degraded": False,
        "executed": False,
        "executed_capabilities": [],
    }


async def test_nonstream_plans_once_and_preserves_failed_seat() -> None:
    originals = {
        "get_knowledge_context": council.get_knowledge_context,
        "collect_external_access": council.collect_external_access,
        "plan_specialist_seats": council.plan_specialist_seats,
        "query_model": council.query_model,
        "stage2_collect_rankings": council.stage2_collect_rankings,
        "calculate_aggregate_rankings": council.calculate_aggregate_rankings,
        "stage3_synthesize_final": council.stage3_synthesize_final,
    }

    plan_calls = []
    model_calls = []
    raw_query = "Review SEO, Wix and product-page conversion."

    def fake_get_knowledge_context(query):
        require(
            query == raw_query,
            f"Knowledge retrieval lost raw-query boundary: {query!r}",
        )
        return ""

    async def fake_collect_access(user_query, conversation_context=""):
        require(
            user_query == raw_query,
            f"Access lost raw-query boundary: {user_query!r}",
        )
        return "", empty_access_metadata()

    def counting_plan(user_query, models, conversation_context=""):
        plan_calls.append(
            {
                "query": user_query,
                "models": list(models),
                "context": conversation_context,
            }
        )
        return originals["plan_specialist_seats"](
            user_query,
            models,
            conversation_context,
        )

    async def fake_query_model(model, messages, *args, **kwargs):
        model_calls.append(model)
        if model == COUNCIL_MODELS[-1]:
            return None
        return {
            "content": f"answer from {model}",
            "model": model,
        }

    async def fake_stage2(user_query, stage1_results):
        return [], {
            f"Response {chr(65 + index)}": result["model"]
            for index, result in enumerate(stage1_results)
        }

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
    council.collect_external_access = fake_collect_access
    council.plan_specialist_seats = counting_plan
    council.query_model = fake_query_model
    council.stage2_collect_rankings = fake_stage2
    council.calculate_aggregate_rankings = fake_aggregate
    council.stage3_synthesize_final = fake_stage3

    try:
        stage1, _stage2, _stage3, metadata = await council.run_full_council(
            raw_query
        )
    finally:
        for name, value in originals.items():
            setattr(council, name, value)

    require(
        len(plan_calls) == 1,
        f"Specialist router ran {len(plan_calls)} times instead of once: {plan_calls!r}",
    )
    require(
        model_calls == COUNCIL_MODELS,
        f"Stage 1 changed normal model calls: {model_calls!r}",
    )
    require(
        len(stage1) == 2,
        f"One failed seat should produce two responses: {stage1!r}",
    )

    specialists = metadata.get("specialists", {})
    require(
        specialists.get("router_version") == "rules-v1",
        f"Missing router version: {specialists!r}",
    )
    require(
        specialists.get("selected_roles")
        == ["seo_strategist", "wix_specialist", "ecommerce_cro"],
        f"Unexpected roles: {specialists!r}",
    )
    require(
        specialists.get("defaulted") is False,
        f"Signalled route was incorrectly defaulted: {specialists!r}",
    )
    require(
        specialists.get("degraded") is True,
        f"Failed seat did not mark metadata degraded: {specialists!r}",
    )

    assignments = specialists.get("assignments", [])
    require(
        len(assignments) == 3,
        f"Planned failed seat disappeared: {assignments!r}",
    )
    require(
        [item.get("responded") for item in assignments]
        == [True, True, False],
        f"Per-seat response status is incorrect: {assignments!r}",
    )
    require(
        [item.get("seat") for item in assignments] == ["A", "B", "C"],
        f"Seat identity changed: {assignments!r}",
    )
    require(
        "scores" not in specialists,
        f"Diagnostic scores leaked into metadata: {specialists!r}",
    )
    require(
        "prompt" not in json.dumps(specialists).lower(),
        f"Prompt material leaked into metadata: {specialists!r}",
    )


async def test_streaming_persists_defaulted_specialist_metadata() -> None:
    storage = main_api.storage
    originals = {
        "get_conversation": storage.get_conversation,
        "add_user_message": storage.add_user_message,
        "add_assistant_message": storage.add_assistant_message,
        "get_knowledge_context": main_api.get_knowledge_context,
        "collect_external_access": main_api.collect_external_access,
        "plan_specialist_seats_main": main_api.plan_specialist_seats,
        "plan_specialist_seats_council": council.plan_specialist_seats,
        "query_model": council.query_model,
        "stage2_collect_rankings": main_api.stage2_collect_rankings,
        "calculate_aggregate_rankings": main_api.calculate_aggregate_rankings,
        "stage3_synthesize_final": main_api.stage3_synthesize_final,
    }

    raw_query = "What should we focus on next?"
    previous_messages = [
        {
            "role": "user",
            "content": "We were discussing general business priorities.",
        }
    ]
    expected_context = build_conversation_context(previous_messages)
    captured = {}
    plan_calls = []
    model_calls = []

    def fake_get_conversation(conversation_id):
        return {
            "id": conversation_id,
            "title": "Existing Conversation",
            "created_at": "2026-09-05T00:00:00",
            "messages": previous_messages,
        }

    def no_op(*args, **kwargs):
        return None

    def fake_add_assistant_message(
        conversation_id,
        stage1,
        stage2,
        stage3,
        metadata,
    ):
        captured["persisted_metadata"] = metadata

    def fake_get_knowledge_context(query):
        require(query == raw_query, "Streaming knowledge lost raw query.")
        return ""

    async def fake_collect_access(user_query, conversation_context=""):
        require(user_query == raw_query, "Streaming access lost raw query.")
        require(
            conversation_context == expected_context,
            "Streaming access lost conversation context.",
        )
        return "", empty_access_metadata()

    def counting_main_plan(user_query, models, conversation_context=""):
        plan_calls.append(
            {
                "query": user_query,
                "models": list(models),
                "context": conversation_context,
            }
        )
        return originals["plan_specialist_seats_main"](
            user_query,
            models,
            conversation_context,
        )

    def forbidden_stage1_reroute(*args, **kwargs):
        raise AssertionError(
            "Stage 1 rerouted specialists instead of reusing the orchestration plan."
        )

    async def fake_query_model(model, messages, *args, **kwargs):
        model_calls.append(model)
        return {
            "content": f"answer from {model}",
            "model": model,
        }

    async def fake_stage2(user_query, stage1_results):
        return [], {
            f"Response {chr(65 + index)}": result["model"]
            for index, result in enumerate(stage1_results)
        }

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
    storage.add_assistant_message = fake_add_assistant_message
    main_api.get_knowledge_context = fake_get_knowledge_context
    main_api.collect_external_access = fake_collect_access
    main_api.plan_specialist_seats = counting_main_plan
    council.plan_specialist_seats = forbidden_stage1_reroute
    council.query_model = fake_query_model
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
        storage.add_assistant_message = originals["add_assistant_message"]
        main_api.get_knowledge_context = originals["get_knowledge_context"]
        main_api.collect_external_access = originals["collect_external_access"]
        main_api.plan_specialist_seats = originals[
            "plan_specialist_seats_main"
        ]
        council.plan_specialist_seats = originals[
            "plan_specialist_seats_council"
        ]
        council.query_model = originals["query_model"]
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
        chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        for chunk in chunks
    )

    require(
        '"type": "error"' not in stream_text,
        f"Streaming emitted an error: {stream_text}",
    )
    require(
        len(plan_calls) == 1,
        f"Streaming router ran {len(plan_calls)} times: {plan_calls!r}",
    )
    require(
        model_calls == COUNCIL_MODELS,
        f"Streaming changed normal Stage 1 calls: {model_calls!r}",
    )

    specialists = captured.get("persisted_metadata", {}).get(
        "specialists", {}
    )
    require(
        specialists.get("selected_roles")
        == [
            "uk_market_analyst",
            "ecommerce_cro",
            "brand_guardian",
        ],
        f"Signal-free route lost defaults: {specialists!r}",
    )
    require(
        specialists.get("defaulted") is True,
        f"Signal-free route was not marked defaulted: {specialists!r}",
    )
    require(
        specialists.get("degraded") is False,
        f"Successful default route was degraded: {specialists!r}",
    )
    require(
        all(
            assignment.get("responded") is True
            for assignment in specialists.get("assignments", [])
        ),
        f"Successful seats were not marked responded: {specialists!r}",
    )
    require(
        "scores" not in specialists,
        f"Diagnostic scores leaked into persistence: {specialists!r}",
    )
    require(
        '"specialists"' in stream_text,
        "Stage 2 streaming metadata did not expose specialist metadata.",
    )


async def main() -> None:
    await test_nonstream_plans_once_and_preserves_failed_seat()
    print(
        "PASS  non-stream Council plans specialists once and preserves failed seat metadata"
    )

    await test_streaming_persists_defaulted_specialist_metadata()
    print(
        "PASS  streaming Council persists compact defaulted specialist metadata without rerouting"
    )

    print("\nSpecialist metadata integration tests PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
