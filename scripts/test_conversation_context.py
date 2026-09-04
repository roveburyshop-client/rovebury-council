"""Deterministic tests for bounded conversation context."""

from __future__ import annotations

import asyncio

import backend.council as council
from backend.conversation_context import (
    build_contextual_query,
    build_conversation_context,
)

CURRENT_QUERY = (
    "What temporary code and temporary Wix label did I give you "
    "in my previous message?"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fixture_context() -> str:
    messages = [
        {"role": "user", "content": "An older unrelated turn."},
        {
            "role": "assistant",
            "stage1": [{"response": "STAGE1_NOISE"}],
            "stage2": [{"ranking": "STAGE2_NOISE"}],
            "stage3": {"response": "An older final answer."},
        },
        {
            "role": "user",
            "content": (
                "For this conversation only: code 48271 and Wix label "
                "Blue Lantern. Do not add these values to ROVEBURY knowledge."
            ),
        },
        {
            "role": "assistant",
            "stage1": [{"response": "RECENT_STAGE1_NOISE"}],
            "stage2": [{"ranking": "RECENT_STAGE2_NOISE"}],
            "stage3": {
                "response": (
                    "Confirmed for this conversation only: 48271 and "
                    "Blue Lantern."
                )
            },
        },
    ]

    context = build_conversation_context(messages)
    require("48271" in context, "Temporary code missing from context.")
    require("Blue Lantern" in context, "Temporary label missing from context.")

    for forbidden in (
        "STAGE1_NOISE",
        "STAGE2_NOISE",
        "RECENT_STAGE1_NOISE",
        "RECENT_STAGE2_NOISE",
    ):
        require(
            forbidden not in context,
            f"Non-final Council content leaked: {forbidden}",
        )

    return context


def test_limits() -> None:
    messages = [
        {
            "role": "user",
            "content": f"message-{index} " + ("x" * 200),
        }
        for index in range(20)
    ]

    context = build_conversation_context(
        messages,
        max_messages=4,
        max_chars=500,
        max_message_chars=160,
    )

    require(len(context) <= 500, "Total character budget exceeded.")
    require("message-19" in context, "Newest message was not retained.")
    require("message-0" not in context, "Oldest message should be excluded.")


def test_contextual_query(context: str) -> None:
    query = build_contextual_query(CURRENT_QUERY, context)
    require("48271" in query, "Contextual query lost temporary code.")
    require("Blue Lantern" in query, "Contextual query lost temporary label.")
    require(CURRENT_QUERY in query, "Current question missing from query.")
    require(
        "transient conversation history" in query,
        "Transient-context rule missing.",
    )


async def test_full_council_routing(context: str) -> None:
    originals = {
        "get_knowledge_context": council.get_knowledge_context,
        "stage1_collect_responses": council.stage1_collect_responses,
        "stage2_collect_rankings": council.stage2_collect_rankings,
        "stage3_synthesize_final": council.stage3_synthesize_final,
    }

    retrieval_queries: list[str] = []
    stage_queries: list[tuple[str, str]] = []

    def fake_get_knowledge(query: str) -> str:
        retrieval_queries.append(query)
        return ""

    async def fake_stage1(query: str, knowledge_context=None):
        stage_queries.append(("stage1", query))
        return [{"model": "model-a", "response": "answer"}]

    async def fake_stage2(query: str, stage1_results):
        stage_queries.append(("stage2", query))
        return (
            [
                {
                    "model": "model-a",
                    "ranking": "FINAL RANKING:\n1. Response A",
                    "parsed_ranking": ["Response A"],
                }
            ],
            {"Response A": "model-a"},
        )

    async def fake_stage3(
        query: str,
        stage1_results,
        stage2_results,
        knowledge_context=None,
    ):
        stage_queries.append(("stage3", query))
        return {
            "model": "chairman",
            "response": "48271 / Blue Lantern",
        }

    council.get_knowledge_context = fake_get_knowledge
    council.stage1_collect_responses = fake_stage1
    council.stage2_collect_rankings = fake_stage2
    council.stage3_synthesize_final = fake_stage3

    try:
        stage1, stage2, stage3, metadata = await council.run_full_council(
            CURRENT_QUERY,
            conversation_context=context,
        )
    finally:
        for name, value in originals.items():
            setattr(council, name, value)

    require(
        retrieval_queries == [CURRENT_QUERY],
        "Knowledge retrieval must use current query only.",
    )
    require(len(stage_queries) == 3, "Expected all three Council stages.")

    for stage_name, query in stage_queries:
        require("48271" in query, f"{stage_name} did not receive code.")
        require("Blue Lantern" in query, f"{stage_name} did not receive label.")
        require(CURRENT_QUERY in query, f"{stage_name} lost current question.")

    context_meta = metadata.get("conversation_context", {})
    require(context_meta.get("used") is True, "Metadata used flag is false.")
    require(
        context_meta.get("characters") == len(context),
        "Metadata character count is wrong.",
    )
    require(stage1 and stage2, "Stubbed Council stages were not returned.")
    require("48271" in stage3.get("response", ""), "Stage 3 stub missing code.")


async def main() -> None:
    context = fixture_context()
    print("PASS  context keeps user messages + Stage 3 only")

    test_limits()
    print("PASS  context respects message and character limits")

    test_contextual_query(context)
    print("PASS  contextual query preserves temporary values")

    await test_full_council_routing(context)
    print("PASS  knowledge retrieval remains current-query only")
    print("PASS  Stage 1 receives conversation context")
    print("PASS  Stage 2 receives conversation context")
    print("PASS  Chairman receives conversation context")
    print("PASS  conversation-context metadata is generated")

    print("\nConversation context tests PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
