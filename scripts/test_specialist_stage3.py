"""Deterministic tests for Specialist Roles Phase 4 Chairman synthesis.

No OpenRouter/network calls are made. Chairman routing is monkeypatched with
local fakes so prompt construction, call count and routing metadata can be
validated directly.
"""

from __future__ import annotations

import asyncio

import backend.council as council
from backend.config import (
    CHAIRMAN_MODEL,
    CHAIRMAN_MODELS,
    COUNCIL_MODELS,
)


STAGE1_FIXTURE = [
    {
        "model": COUNCIL_MODELS[0],
        "seat": "A",
        "role_id": "seo_strategist",
        "role_name": "SEO Strategist",
        "response": (
            "Use governed ROVEBURY facts for internal configuration and "
            "separate them from claims requiring live SEO verification."
        ),
    },
    {
        "model": COUNCIL_MODELS[1],
        "seat": "B",
        "role_id": "wix_specialist",
        "role_name": "Wix Specialist",
        "response": (
            "Preserve implementation constraints and verify current Wix "
            "capabilities before making time-sensitive platform claims."
        ),
    },
    {
        "model": COUNCIL_MODELS[2],
        "seat": "C",
        "role_id": "ecommerce_cro",
        "role_name": "Ecommerce & CRO Strategist",
        "response": (
            "A conversion recommendation may conflict with an SEO priority; "
            "surface the trade-off rather than forcing agreement."
        ),
    },
]

STAGE2_FIXTURE = [
    {
        "model": COUNCIL_MODELS[0],
        "ranking": (
            "Response A is strongest on evidence discipline. "
            "Response C identifies a material trade-off.\n\n"
            "FINAL RANKING:\n"
            "1. Response A\n"
            "2. Response C\n"
            "3. Response B"
        ),
        "parsed_ranking": [
            "Response A",
            "Response C",
            "Response B",
        ],
    },
    {
        "model": COUNCIL_MODELS[1],
        "ranking": (
            "Response B is strongest on implementation risk. "
            "Response A is stronger on internal-fact discipline.\n\n"
            "FINAL RANKING:\n"
            "1. Response B\n"
            "2. Response A\n"
            "3. Response C"
        ),
        "parsed_ranking": [
            "Response B",
            "Response A",
            "Response C",
        ],
    },
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def test_role_aware_model_anonymous_chairman() -> None:
    original_query = council.query_model_with_fallback
    original_knowledge = council.get_knowledge_context
    calls = []

    def forbidden_retrieval(query):
        raise AssertionError(
            "Stage 3 performed a second knowledge retrieval despite "
            "receiving pre-retrieved knowledge."
        )

    async def fake_query_model_with_fallback(
        models,
        messages,
        *args,
        **kwargs,
    ):
        calls.append(
            {
                "models": list(models),
                "messages": messages,
            }
        )
        return {
            "content": "synthetic chairman answer",
            "model": "provider/actual-chairman-route",
            "primary_model": CHAIRMAN_MODEL,
            "route_model": "provider/actual-chairman-route",
            "fallback_used": True,
        }

    council.query_model_with_fallback = (
        fake_query_model_with_fallback
    )
    council.get_knowledge_context = forbidden_retrieval

    knowledge_context = (
        "[Knowledge source: decisions/DEC-001.md]\n"
        "Internal fixture: United Kingdom is the primary market."
    )

    try:
        result = await council.stage3_synthesize_final(
            "What should ROVEBURY prioritise?",
            STAGE1_FIXTURE,
            STAGE2_FIXTURE,
            knowledge_context,
        )
    finally:
        council.query_model_with_fallback = original_query
        council.get_knowledge_context = original_knowledge

    require(
        len(calls) == 1,
        (
            "Stage 3 changed the normal Chairman invocation count: "
            f"{len(calls)}."
        ),
    )
    require(
        calls[0]["models"] == CHAIRMAN_MODELS,
        (
            "Chairman fallback chain changed: "
            f"{calls[0]['models']!r}."
        ),
    )
    require(
        len(calls[0]["messages"]) == 1,
        "Chairman should receive one synthesized user prompt.",
    )

    prompt = calls[0]["messages"][0]["content"]

    expected_role_markers = (
        "Seat A",
        "Specialist lens: SEO Strategist",
        "Role ID: seo_strategist",
        "Seat B",
        "Specialist lens: Wix Specialist",
        "Role ID: wix_specialist",
        "Seat C",
        "Specialist lens: Ecommerce & CRO Strategist",
        "Role ID: ecommerce_cro",
    )

    for marker in expected_role_markers:
        require(
            marker in prompt,
            f"Chairman prompt lost specialist context: {marker!r}",
        )

    for item in STAGE1_FIXTURE:
        require(
            item["response"] in prompt,
            f"Chairman prompt lost Stage 1 contribution: {item!r}",
        )

    for item in STAGE2_FIXTURE:
        require(
            item["ranking"] in prompt,
            f"Chairman prompt lost Stage 2 peer review: {item!r}",
        )

    leaked_ids = sorted(
        {
            *COUNCIL_MODELS,
            *CHAIRMAN_MODELS,
        }
    )

    for model_id in leaked_ids:
        require(
            model_id not in prompt,
            (
                "Model identity leaked from Council metadata into the "
                f"Chairman prompt: {model_id}"
            ),
        )

    required_contract_phrases = (
        "Specialist roles are analytical lenses, not authorities and not evidence.",
        "Peer reviews, rankings and consensus are quality signals only",
        "Preserve material disagreements, uncertainties and trade-offs",
        "may corroborate one another internally",
        "MUST NOT be described as independent external confirmation",
        '"independently confirmed"',
        "need for current verification",
        "without exposing or inferring the identity of any underlying AI model",
    )

    for phrase in required_contract_phrases:
        require(
            phrase in prompt,
            f"Chairman contract missing required rule: {phrase!r}",
        )

    require(
        knowledge_context in prompt,
        "Chairman prompt lost pre-retrieved governed knowledge.",
    )

    require(
        result["model"] == "provider/actual-chairman-route",
        f"Actual Chairman route was not preserved: {result!r}",
    )
    require(
        result["primary_model"] == CHAIRMAN_MODEL,
        f"primary_model metadata changed: {result!r}",
    )
    require(
        result["route_model"]
        == "provider/actual-chairman-route",
        f"route_model metadata changed: {result!r}",
    )
    require(
        result["fallback_used"] is True,
        f"fallback_used metadata changed: {result!r}",
    )


async def test_legacy_stage1_role_fallback() -> None:
    original_query = council.query_model_with_fallback
    captured = {}

    async def fake_query_model_with_fallback(
        models,
        messages,
        *args,
        **kwargs,
    ):
        captured["messages"] = messages
        return {
            "content": "legacy-safe final",
            "model": CHAIRMAN_MODEL,
            "primary_model": CHAIRMAN_MODEL,
            "route_model": CHAIRMAN_MODEL,
            "fallback_used": False,
        }

    council.query_model_with_fallback = (
        fake_query_model_with_fallback
    )

    try:
        await council.stage3_synthesize_final(
            "Legacy compatibility check.",
            [
                {
                    "model": "legacy/model-id",
                    "response": "legacy contribution",
                }
            ],
            [],
            "",
        )
    finally:
        council.query_model_with_fallback = original_query

    prompt = captured["messages"][0]["content"]

    require(
        "Seat A" in prompt,
        "Legacy Stage 1 result did not receive deterministic seat fallback.",
    )
    require(
        "Specialist lens: Council Generalist" in prompt,
        "Legacy Stage 1 result did not receive Generalist role fallback.",
    )
    require(
        "Role ID: generalist" in prompt,
        "Legacy Stage 1 result did not receive generalist role_id fallback.",
    )
    require(
        "legacy/model-id" not in prompt,
        "Legacy model identity leaked into Chairman prompt.",
    )


async def test_chairman_failure_shape_unchanged() -> None:
    original_query = council.query_model_with_fallback
    calls = []

    async def fake_query_model_with_fallback(
        models,
        messages,
        *args,
        **kwargs,
    ):
        calls.append(list(models))
        return None

    council.query_model_with_fallback = (
        fake_query_model_with_fallback
    )

    try:
        result = await council.stage3_synthesize_final(
            "Failure-shape check.",
            [],
            [],
            "",
        )
    finally:
        council.query_model_with_fallback = original_query

    require(
        calls == [CHAIRMAN_MODELS],
        f"Chairman failure path changed fallback candidates: {calls!r}",
    )
    require(
        result == {
            "model": CHAIRMAN_MODEL,
            "response": "Error: Unable to generate final synthesis.",
            "primary_model": CHAIRMAN_MODEL,
            "route_model": None,
            "fallback_used": False,
        },
        f"Chairman failure return shape changed: {result!r}",
    )


async def main() -> None:
    await test_role_aware_model_anonymous_chairman()
    print(
        "PASS  Chairman is role-aware, model-anonymous and uses one fallback call"
    )

    await test_legacy_stage1_role_fallback()
    print(
        "PASS  Chairman preserves legacy Stage 1 compatibility without model leakage"
    )

    await test_chairman_failure_shape_unchanged()
    print(
        "PASS  Chairman fallback failure shape remains compatible"
    )

    print(
        "\nRole-aware Chairman synthesis tests PASSED."
    )


if __name__ == "__main__":
    asyncio.run(main())
