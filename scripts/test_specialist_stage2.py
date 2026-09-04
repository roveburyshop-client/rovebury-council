"""Deterministic tests for Specialist Roles Stage 2 Critical Peer Review.

No OpenRouter/network calls are made. Council model calls and API stages are
monkeypatched with local fakes.
"""

from __future__ import annotations

import asyncio
import json

import backend.council as council
import backend.main as main_api
from backend.config import COUNCIL_MODELS


STAGE1_FIXTURE = [
    {
        "model": COUNCIL_MODELS[0],
        "seat": "A",
        "role_id": "seo_strategist",
        "role_name": "SEO Strategist",
        "response": (
            "Prioritise search intent and indexable PDP content. "
            "Treat unverified search-volume claims as unknown."
        ),
    },
    {
        "model": COUNCIL_MODELS[1],
        "seat": "B",
        "role_id": "wix_specialist",
        "role_name": "Wix Specialist",
        "response": (
            "Check Wix Stores implementation constraints before changing "
            "structured data or catalogue behaviour."
        ),
    },
    {
        "model": COUNCIL_MODELS[2],
        "seat": "C",
        "role_id": "ecommerce_cro",
        "role_name": "Ecommerce & CRO Strategist",
        "response": (
            "Reduce PDP friction and preserve trust signals while testing "
            "commercial changes."
        ),
    },
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def test_role_aware_model_anonymous_peer_review() -> None:
    original = council.query_models_parallel
    captured = {}

    async def fake_query_models_parallel(models, messages):
        captured["models"] = list(models)
        captured["messages"] = messages

        ranking = (
            "Response A is disciplined.\n"
            "Response B identifies implementation risk.\n"
            "Response C handles conversion trade-offs.\n\n"
            "FINAL RANKING:\n"
            "1. Response B\n"
            "2. Response A\n"
            "3. Response C"
        )

        return {
            model: {
                "content": ranking,
                "model": model,
            }
            for model in models
        }

    council.query_models_parallel = fake_query_models_parallel

    try:
        stage2_results, label_to_model = (
            await council.stage2_collect_rankings(
                "Improve this ROVEBURY product page.",
                STAGE1_FIXTURE,
            )
        )
    finally:
        council.query_models_parallel = original

    require(
        captured["models"] == COUNCIL_MODELS,
        "Stage 2 changed the normal Council model set or call count.",
    )
    require(
        len(captured["messages"]) == 1,
        "Stage 2 should send one shared peer-review prompt.",
    )

    prompt = captured["messages"][0]["content"]

    for item in STAGE1_FIXTURE:
        require(
            item["role_name"] in prompt,
            f"Missing specialist lens in peer-review prompt: {item!r}",
        )

    for model in COUNCIL_MODELS:
        require(
            model not in prompt,
            (
                "Council model identity leaked into peer-review prompt: "
                + model
            ),
        )

    required_contract_phrases = (
        "analytical perspective, not as evidence",
        "peer consensus as verification",
        "Preserve material disagreements and trade-offs",
        "Do not infer or discuss which underlying AI model",
        "FINAL RANKING:",
    )

    for phrase in required_contract_phrases:
        require(
            phrase in prompt,
            f"Critical Peer Review contract missing: {phrase!r}",
        )

    expected_label_to_model = {
        "Response A": COUNCIL_MODELS[0],
        "Response B": COUNCIL_MODELS[1],
        "Response C": COUNCIL_MODELS[2],
    }
    require(
        label_to_model == expected_label_to_model,
        f"label_to_model compatibility changed: {label_to_model!r}",
    )
    require(
        len(stage2_results) == len(COUNCIL_MODELS),
        f"Expected one ranking per Council model: {stage2_results!r}",
    )

    for result in stage2_results:
        require(
            result["parsed_ranking"]
            == [
                "Response B",
                "Response A",
                "Response C",
            ],
            f"FINAL RANKING parser compatibility broke: {result!r}",
        )


def test_label_to_role_contract() -> None:
    mapping = council.build_label_to_role(
        STAGE1_FIXTURE
    )

    require(
        mapping == {
            "Response A": {
                "role_id": "seo_strategist",
                "role_name": "SEO Strategist",
            },
            "Response B": {
                "role_id": "wix_specialist",
                "role_name": "Wix Specialist",
            },
            "Response C": {
                "role_id": "ecommerce_cro",
                "role_name": "Ecommerce & CRO Strategist",
            },
        },
        f"Unexpected label_to_role mapping: {mapping!r}",
    )

    legacy = council.build_label_to_role(
        [
            {
                "model": "legacy/model",
                "response": "legacy response",
            }
        ]
    )

    require(
        legacy == {
            "Response A": {
                "role_id": "generalist",
                "role_name": "Council Generalist",
            }
        },
        f"Legacy Stage 1 compatibility broke: {legacy!r}",
    )


async def test_non_stream_metadata_adds_label_to_role() -> None:
    originals = {
        "get_knowledge_context": council.get_knowledge_context,
        "stage1_collect_responses": council.stage1_collect_responses,
        "stage2_collect_rankings": council.stage2_collect_rankings,
        "calculate_aggregate_rankings": council.calculate_aggregate_rankings,
        "stage3_synthesize_final": council.stage3_synthesize_final,
    }

    def fake_get_knowledge_context(query):
        return ""

    async def fake_stage1(*args, **kwargs):
        return STAGE1_FIXTURE

    async def fake_stage2(user_query, stage1_results):
        return (
            [],
            {
                "Response A": COUNCIL_MODELS[0],
                "Response B": COUNCIL_MODELS[1],
                "Response C": COUNCIL_MODELS[2],
            },
        )

    def fake_aggregate(stage2_results, label_to_model):
        return []

    async def fake_stage3(*args, **kwargs):
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
        _, _, _, metadata = await council.run_full_council(
            "Improve the product page."
        )
    finally:
        for name, value in originals.items():
            setattr(council, name, value)

    require(
        metadata["label_to_role"]
        == council.build_label_to_role(STAGE1_FIXTURE),
        f"Non-stream metadata lost label_to_role: {metadata!r}",
    )


async def test_streaming_metadata_persists_label_to_role() -> None:
    storage = main_api.storage
    originals = {
        "get_conversation": storage.get_conversation,
        "add_user_message": storage.add_user_message,
        "add_assistant_message": storage.add_assistant_message,
        "get_knowledge_context": main_api.get_knowledge_context,
        "stage1_collect_responses": main_api.stage1_collect_responses,
        "stage2_collect_rankings": main_api.stage2_collect_rankings,
        "calculate_aggregate_rankings": main_api.calculate_aggregate_rankings,
        "stage3_synthesize_final": main_api.stage3_synthesize_final,
    }

    persisted = {}

    def fake_get_conversation(conversation_id):
        return {
            "id": conversation_id,
            "created_at": "2026-09-04T00:00:00",
            "title": "Existing",
            "messages": [
                {
                    "role": "user",
                    "content": "Earlier context.",
                }
            ],
        }

    def no_op(*args, **kwargs):
        return None

    def fake_add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result,
        metadata,
    ):
        persisted["metadata"] = metadata

    def fake_get_knowledge_context(query):
        return ""

    async def fake_stage1(*args, **kwargs):
        return STAGE1_FIXTURE

    async def fake_stage2(user_query, stage1_results):
        return (
            [],
            {
                "Response A": COUNCIL_MODELS[0],
                "Response B": COUNCIL_MODELS[1],
                "Response C": COUNCIL_MODELS[2],
            },
        )

    def fake_aggregate(stage2_results, label_to_model):
        return []

    async def fake_stage3(*args, **kwargs):
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
    main_api.stage1_collect_responses = fake_stage1
    main_api.stage2_collect_rankings = fake_stage2
    main_api.calculate_aggregate_rankings = fake_aggregate
    main_api.stage3_synthesize_final = fake_stage3

    try:
        response = await main_api.send_message_stream(
            "test-conversation",
            main_api.SendMessageRequest(
                content="Improve the product page."
            ),
        )

        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(
                chunk.decode("utf-8")
                if isinstance(chunk, bytes)
                else chunk
            )
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

    events = []

    for chunk in chunks:
        for line in chunk.splitlines():
            if not line.startswith("data: "):
                continue
            events.append(
                json.loads(line[len("data: "):])
            )

    stage2_complete = next(
        (
            event
            for event in events
            if event.get("type") == "stage2_complete"
        ),
        None,
    )

    require(
        stage2_complete is not None,
        f"Streaming test missed stage2_complete: {events!r}",
    )

    expected = council.build_label_to_role(
        STAGE1_FIXTURE
    )

    require(
        stage2_complete["metadata"]["label_to_role"] == expected,
        (
            "stage2_complete metadata lost label_to_role: "
            f"{stage2_complete!r}"
        ),
    )
    require(
        persisted["metadata"]["label_to_role"] == expected,
        (
            "Persisted assistant metadata lost label_to_role: "
            f"{persisted!r}"
        ),
    )


async def main() -> None:
    await test_role_aware_model_anonymous_peer_review()
    print("PASS  Stage 2 is role-aware and model-anonymous")

    test_label_to_role_contract()
    print("PASS  label_to_role mapping and legacy fallback")

    await test_non_stream_metadata_adds_label_to_role()
    print("PASS  non-stream metadata includes label_to_role")

    await test_streaming_metadata_persists_label_to_role()
    print("PASS  streaming metadata persists label_to_role")

    print(
        "\nSpecialist Stage 2 Critical Peer Review tests PASSED."
    )


if __name__ == "__main__":
    asyncio.run(main())
