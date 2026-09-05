"""Deterministic tests for controlled-access Council integration.

No real GitHub, OpenRouter, web, Wix or supplier calls are made.
"""

from __future__ import annotations

import asyncio
import json

import backend.council as council
import backend.main as main_api
from backend.access import (
    CAPABILITY_GITHUB,
    AccessProviderRegistry,
)
from backend.access_runtime import (
    build_access_augmented_query,
    collect_external_access,
)
from backend.conversation_context import (
    build_contextual_query,
    build_conversation_context,
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


async def test_runtime_provider_boundary() -> None:
    registry = AccessProviderRegistry()
    calls = []

    async def provider(request):
        calls.append(
            dict(request)
        )
        return [
            {
                "source_name": "GitHub fixture",
                "locator": "https://example.invalid/commit/abc",
                "observed_at": "2026-09-05T00:00:00Z",
                "content": "Latest commit: abc1234",
            }
        ]

    registry.register(
        CAPABILITY_GITHUB,
        provider,
    )

    raw_query = (
        "Check GitHub for the latest commit on branch rovebury-dev."
    )
    private_context = (
        "[User message]\n"
        "PRIVATE_CONTEXT_MUST_NOT_REACH_PROVIDER"
    )

    access_context, metadata = (
        await collect_external_access(
            raw_query,
            private_context,
            registry=registry,
        )
    )

    require(
        calls
        == [
            {
                "capability": CAPABILITY_GITHUB,
                "query": raw_query,
                "router_version": "access-rules-v1",
            }
        ],
        f"Provider boundary changed: {calls!r}",
    )
    require(
        "PRIVATE_CONTEXT_MUST_NOT_REACH_PROVIDER"
        not in json.dumps(calls),
        "Conversation context leaked into provider request.",
    )
    require(
        "Latest commit: abc1234"
        in access_context,
        f"Live evidence did not reach access context: {access_context!r}",
    )
    require(
        metadata["executed"] is True,
        f"Required GitHub access was not executed: {metadata!r}",
    )
    require(
        metadata["degraded"] is False,
        f"Successful GitHub access was incorrectly degraded: {metadata!r}",
    )
    require(
        '"content"'
        not in json.dumps(metadata),
        f"Evidence body leaked into access metadata: {metadata!r}",
    )


async def test_nonstream_council_preserves_boundaries_and_metadata() -> None:
    originals = {
        "get_knowledge_context": council.get_knowledge_context,
        "collect_external_access": council.collect_external_access,
        "stage1_collect_responses": council.stage1_collect_responses,
        "stage2_collect_rankings": council.stage2_collect_rankings,
        "calculate_aggregate_rankings": council.calculate_aggregate_rankings,
        "stage3_synthesize_final": council.stage3_synthesize_final,
    }
    captured = {}

    raw_query = (
        "Check GitHub for the latest commit on branch rovebury-dev."
    )
    conversation_context = (
        "[User message]\nEarlier we discussed Wix."
    )
    evidence_marker = "LIVE_GITHUB_EVIDENCE_FIXTURE"

    def fake_get_knowledge_context(query):
        captured["knowledge_query"] = query
        return "PRE_RETRIEVED_KNOWLEDGE"

    async def fake_collect_access(
        user_query,
        context="",
        **kwargs,
    ):
        captured["access_query"] = user_query
        captured["access_context_input"] = context
        return (
            (
                "ACCESS STATUS (SYSTEM-GENERATED):\n"
                f"{evidence_marker}"
            ),
            {
                "router_version": "access-rules-v1",
                "mode": "required",
                "required": True,
                "blocked_by_user": False,
                "requested_capabilities": ["github"],
                "sources_used": [
                    {
                        "capability": "github",
                        "source_name": "fixture",
                        "locator": "https://example.invalid/commit/abc",
                        "observed_at": "fixture",
                    }
                ],
                "failures": [],
                "missing_capabilities": [],
                "degraded": False,
                "executed": True,
                "executed_capabilities": ["github"],
            },
        )

    async def fake_stage1(
        user_query,
        knowledge_context=None,
        *,
        routing_query=None,
        conversation_context="",
    ):
        captured["stage1_query"] = user_query
        captured["stage1_knowledge"] = knowledge_context
        captured["stage1_routing_query"] = routing_query
        return [
            {
                "model": "model/a",
                "seat": "A",
                "role_id": "seo_strategist",
                "role_name": "SEO Strategist",
                "response": "answer",
            }
        ]

    async def fake_stage2(
        user_query,
        stage1_results,
    ):
        captured["stage2_query"] = user_query
        return [], {
            "Response A": "model/a"
        }

    def fake_aggregate(
        stage2_results,
        label_to_model,
    ):
        return []

    async def fake_stage3(
        user_query,
        stage1_results,
        stage2_results,
        knowledge_context=None,
    ):
        captured["stage3_query"] = user_query
        captured["stage3_knowledge"] = knowledge_context
        return {
            "model": "chairman/model",
            "response": "final",
            "primary_model": "chairman/model",
            "route_model": "chairman/model",
            "fallback_used": False,
        }

    council.get_knowledge_context = fake_get_knowledge_context
    council.collect_external_access = fake_collect_access
    council.stage1_collect_responses = fake_stage1
    council.stage2_collect_rankings = fake_stage2
    council.calculate_aggregate_rankings = fake_aggregate
    council.stage3_synthesize_final = fake_stage3

    try:
        _s1, _s2, _s3, metadata = (
            await council.run_full_council(
                raw_query,
                conversation_context,
            )
        )
    finally:
        for name, value in originals.items():
            setattr(
                council,
                name,
                value,
            )

    require(
        captured["knowledge_query"]
        == raw_query,
        "Governed knowledge retrieval no longer uses the raw current query.",
    )
    require(
        captured["access_query"]
        == raw_query,
        "Access planner/runtime did not receive the raw current query.",
    )
    require(
        captured["access_context_input"]
        == conversation_context,
        "Access planner lost transient conversation context.",
    )
    require(
        captured["stage1_routing_query"]
        == raw_query,
        "Specialist routing no longer receives the raw current query.",
    )

    expected_base = build_contextual_query(
        raw_query,
        conversation_context,
    )
    expected_query = build_access_augmented_query(
        expected_base,
        (
            "ACCESS STATUS (SYSTEM-GENERATED):\n"
            f"{evidence_marker}"
        ),
    )

    require(
        captured["stage1_query"]
        == expected_query,
        "Stage 1 did not receive contextual query plus controlled access.",
    )
    require(
        captured["stage2_query"]
        == expected_query,
        "Stage 2 did not receive controlled external evidence.",
    )
    require(
        captured["stage3_query"]
        == expected_query,
        "Chairman did not receive controlled external evidence.",
    )
    require(
        captured["stage1_knowledge"]
        == "PRE_RETRIEVED_KNOWLEDGE",
        "Stage 1 stopped reusing pre-retrieved governed knowledge.",
    )
    require(
        captured["stage3_knowledge"]
        == "PRE_RETRIEVED_KNOWLEDGE",
        "Stage 3 stopped reusing pre-retrieved governed knowledge.",
    )
    require(
        metadata["access"]["executed"]
        is True,
        f"Access metadata was not returned: {metadata!r}",
    )


async def test_streaming_persists_access_metadata() -> None:
    storage = main_api.storage

    originals = {
        "get_conversation": storage.get_conversation,
        "add_user_message": storage.add_user_message,
        "add_assistant_message": storage.add_assistant_message,
        "get_knowledge_context": main_api.get_knowledge_context,
        "collect_external_access": main_api.collect_external_access,
        "stage1_collect_responses": main_api.stage1_collect_responses,
        "stage2_collect_rankings": main_api.stage2_collect_rankings,
        "calculate_aggregate_rankings": main_api.calculate_aggregate_rankings,
        "stage3_synthesize_final": main_api.stage3_synthesize_final,
    }

    captured = {}
    raw_query = (
        "Check GitHub for the latest commit on branch rovebury-dev."
    )
    previous_messages = [
        {
            "role": "user",
            "content": "Earlier context.",
        }
    ]
    expected_context = build_conversation_context(
        previous_messages
    )
    evidence_marker = "STREAM_GITHUB_EVIDENCE"

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
        captured["knowledge_query"] = query
        return "STREAM_KNOWLEDGE"

    async def fake_collect_access(
        user_query,
        context="",
        **kwargs,
    ):
        captured["access_query"] = user_query
        captured["access_context"] = context
        return (
            evidence_marker,
            {
                "router_version": "access-rules-v1",
                "mode": "required",
                "required": True,
                "blocked_by_user": False,
                "requested_capabilities": ["github"],
                "sources_used": [
                    {
                        "capability": "github",
                        "source_name": "fixture",
                        "locator": "https://example.invalid/commit/abc",
                        "observed_at": "fixture",
                    }
                ],
                "failures": [],
                "missing_capabilities": [],
                "degraded": False,
                "executed": True,
                "executed_capabilities": ["github"],
            },
        )

    async def fake_stage1(
        user_query,
        knowledge_context=None,
        *,
        routing_query=None,
        conversation_context="",
    ):
        captured["stage1_query"] = user_query
        captured["stage1_routing_query"] = routing_query
        return [
            {
                "model": "model/a",
                "seat": "A",
                "role_id": "seo_strategist",
                "role_name": "SEO Strategist",
                "response": "answer",
            }
        ]

    async def fake_stage2(
        user_query,
        stage1_results,
    ):
        return [], {
            "Response A": "model/a"
        }

    def fake_aggregate(
        stage2_results,
        label_to_model,
    ):
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
    main_api.stage1_collect_responses = fake_stage1
    main_api.stage2_collect_rankings = fake_stage2
    main_api.calculate_aggregate_rankings = fake_aggregate
    main_api.stage3_synthesize_final = fake_stage3

    try:
        response = await main_api.send_message_stream(
            "test-conversation",
            main_api.SendMessageRequest(
                content=raw_query
            ),
        )

        chunks = []

        async for chunk in response.body_iterator:
            chunks.append(
                chunk
            )
    finally:
        storage.get_conversation = originals["get_conversation"]
        storage.add_user_message = originals["add_user_message"]
        storage.add_assistant_message = originals["add_assistant_message"]
        main_api.get_knowledge_context = originals["get_knowledge_context"]
        main_api.collect_external_access = originals["collect_external_access"]
        main_api.stage1_collect_responses = originals["stage1_collect_responses"]
        main_api.stage2_collect_rankings = originals["stage2_collect_rankings"]
        main_api.calculate_aggregate_rankings = originals[
            "calculate_aggregate_rankings"
        ]
        main_api.stage3_synthesize_final = originals[
            "stage3_synthesize_final"
        ]

    stream_text = "".join(
        chunk.decode("utf-8")
        if isinstance(
            chunk,
            bytes,
        )
        else chunk
        for chunk in chunks
    )

    require(
        '"type": "error"'
        not in stream_text,
        f"Streaming integration emitted an error: {stream_text}",
    )
    require(
        captured["knowledge_query"]
        == raw_query,
        "Streaming governed retrieval lost raw-query boundary.",
    )
    require(
        captured["access_query"]
        == raw_query,
        "Streaming access lost raw-query boundary.",
    )
    require(
        captured["access_context"]
        == expected_context,
        "Streaming access planner lost conversation context.",
    )
    require(
        captured["stage1_routing_query"]
        == raw_query,
        "Streaming specialist routing lost raw-query boundary.",
    )
    require(
        evidence_marker
        in captured["stage1_query"],
        "Streaming Stage 1 did not receive controlled external evidence.",
    )

    persisted = captured.get(
        "persisted_metadata",
        {},
    )

    require(
        persisted.get(
            "access",
            {},
        ).get(
            "executed"
        )
        is True,
        f"Access metadata was not persisted: {persisted!r}",
    )
    require(
        '"content"'
        not in json.dumps(
            persisted.get(
                "access",
                {},
            )
        ),
        f"Evidence body leaked into persisted access metadata: {persisted!r}",
    )
    require(
        '"access"'
        in stream_text,
        "Streaming Stage 2 metadata did not expose access metadata.",
    )


async def test_required_missing_provider_degrades_without_fabrication() -> None:
    raw_query = (
        "Check the current Wix product configuration."
    )

    access_context, metadata = (
        await collect_external_access(
            raw_query,
            "",
            registry=AccessProviderRegistry(),
        )
    )

    require(
        metadata["required"]
        is True,
        f"Live Wix request was not required: {metadata!r}",
    )
    require(
        metadata["degraded"]
        is True,
        f"Missing required provider did not degrade: {metadata!r}",
    )
    require(
        "No usable live external evidence was obtained."
        in access_context,
        f"Missing provider did not produce anti-fabrication context: {access_context!r}",
    )
    require(
        "Do not claim that the requested live fact was verified."
        in access_context,
        f"Missing provider lost verification warning: {access_context!r}",
    )


async def main() -> None:
    await test_runtime_provider_boundary()
    print(
        "PASS  controlled access provider receives raw query only"
    )

    await test_nonstream_council_preserves_boundaries_and_metadata()
    print(
        "PASS  non-stream Council receives evidence without contaminating routing/retrieval"
    )

    await test_streaming_persists_access_metadata()
    print(
        "PASS  streaming Council persists compact access metadata"
    )

    await test_required_missing_provider_degrades_without_fabrication()
    print(
        "PASS  missing required provider degrades with anti-fabrication context"
    )

    print(
        "\nControlled access pipeline integration tests PASSED."
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
