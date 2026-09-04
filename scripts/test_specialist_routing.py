"""Deterministic tests for ROVEBURY specialist-role routing."""

from __future__ import annotations

from backend.specialists import (
    DEFAULT_ROLE_IDS,
    ROLE_BY_ID,
    ROUTER_VERSION,
    SPECIALIST_ROLE_IDS,
    assign_specialist_seats,
    build_specialist_instruction,
    compact_specialist_metadata,
    plan_specialist_seats,
    route_specialists,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_catalogue_contract() -> None:
    expected = {
        "seo_strategist",
        "uk_market_analyst",
        "ecommerce_cro",
        "wix_specialist",
        "sourcing_analyst",
        "brand_guardian",
    }

    require(
        set(SPECIALIST_ROLE_IDS) == expected,
        f"Unexpected specialist catalogue: {SPECIALIST_ROLE_IDS!r}",
    )
    require(
        "generalist" in ROLE_BY_ID,
        "Generalist fallback role is missing.",
    )
    require(
        ROUTER_VERSION == "rules-v1",
        f"Unexpected router version: {ROUTER_VERSION!r}",
    )


def test_seo_wix_product_page_route() -> None:
    result = route_specialists(
        "How should I optimise the SEO of this Wix product page?"
    )

    require(
        result["selected_roles"] == [
            "seo_strategist",
            "wix_specialist",
            "ecommerce_cro",
        ],
        f"Unexpected SEO/Wix/CRO route: {result!r}",
    )
    require(
        result["defaulted"] is False,
        "A strong specialist route must not be marked defaulted.",
    )


def test_aliexpress_uk_product_route() -> None:
    result = route_specialists(
        "Which AliExpress backpack should ROVEBURY sell in the UK?"
    )

    require(
        result["selected_roles"] == [
            "sourcing_analyst",
            "uk_market_analyst",
            "ecommerce_cro",
        ],
        f"Unexpected sourcing/UK/CRO route: {result!r}",
    )


def test_portuguese_route() -> None:
    result = route_specialists(
        "Quero otimizar o SEO da pagina de produto no Wix "
        "para aumentar a conversao."
    )

    require(
        result["selected_roles"] == [
            "ecommerce_cro",
            "seo_strategist",
            "wix_specialist",
        ],
        f"Unexpected Portuguese route: {result!r}",
    )


def test_current_query_precedes_conversation_context() -> None:
    result = route_specialists(
        user_query=(
            "How should the Wix SEO and product page structure be improved?"
        ),
        conversation_context=(
            "Earlier we discussed AliExpress suppliers, dropshipping, "
            "shipping, variants, margins, UK consumers and British demand."
        ),
    )

    require(
        set(result["selected_roles"]) == {
            "seo_strategist",
            "wix_specialist",
            "ecommerce_cro",
        },
        "Conversation context overrode stronger current-query signals: "
        f"{result!r}",
    )
    require(
        "sourcing_analyst" not in result["selected_roles"]
        and "uk_market_analyst" not in result["selected_roles"],
        "Context-only roles displaced current-query roles: "
        f"{result!r}",
    )


def test_follow_up_uses_conversation_context() -> None:
    result = route_specialists(
        user_query="What about the product page itself?",
        conversation_context=(
            "We are discussing the SEO strategy for a cabin backpack on Wix."
        ),
    )

    require(
        result["selected_roles"] == [
            "ecommerce_cro",
            "seo_strategist",
            "wix_specialist",
        ],
        f"Follow-up did not use context correctly: {result!r}",
    )


def test_default_business_trio() -> None:
    result = route_specialists(
        "Think through this general business question for ROVEBURY."
    )

    require(
        result["selected_roles"] == list(DEFAULT_ROLE_IDS),
        f"Unexpected default trio: {result!r}",
    )
    require(
        result["defaulted"] is True,
        "Signal-free route should be marked defaulted.",
    )


def test_routing_is_deterministic() -> None:
    query = "Review the Wix SEO and conversion setup for this product page."
    context = "ROVEBURY is preparing the UK launch."

    first = route_specialists(query, context)

    for _ in range(20):
        require(
            route_specialists(query, context) == first,
            "Same routing input produced a different output.",
        )


def test_seat_assignment_contract() -> None:
    models = [
        "model/a",
        "model/b",
        "model/c",
    ]

    routing, seats = plan_specialist_seats(
        "Review SEO, Wix and product-page conversion.",
        models,
    )

    require(
        len(seats) == 3,
        f"Expected 3 seats, got {len(seats)}.",
    )
    require(
        [seat["seat"] for seat in seats] == ["A", "B", "C"],
        f"Unexpected seat labels: {seats!r}",
    )
    require(
        len({seat["role_id"] for seat in seats}) == 3,
        f"Seat roles are not unique: {seats!r}",
    )
    require(
        [seat["model"] for seat in seats] == models,
        f"Models were reordered unexpectedly: {seats!r}",
    )
    require(
        [seat["role_id"] for seat in seats]
        == routing["selected_roles"],
        f"Seat assignment differs from routing: {seats!r}",
    )


def test_compact_metadata_excludes_scores_and_tracks_degradation() -> None:
    routing = route_specialists(
        "Review SEO, Wix and product-page conversion."
    )
    seats = assign_specialist_seats(
        routing["selected_roles"],
        ["model/a", "model/b", "model/c"],
    )

    metadata = compact_specialist_metadata(
        routing,
        seats,
        responded_models=["model/a", "model/b"],
    )

    require(
        "scores" not in metadata,
        "Diagnostic routing scores leaked into persistent metadata.",
    )
    require(
        metadata["degraded"] is True,
        "One failed seat should mark specialist metadata degraded.",
    )
    require(
        metadata["assignments"][2]["responded"] is False,
        f"Failed seat was not recorded correctly: {metadata!r}",
    )


def test_specialist_instruction_preserves_evidence_boundaries() -> None:
    instruction = build_specialist_instruction("seo_strategist")

    required_phrases = (
        "SEO Strategist",
        "analytical perspective, not independent evidence",
        "Agreement between specialists is not verification",
        "governed ROVEBURY knowledge takes precedence",
    )

    for phrase in required_phrases:
        require(
            phrase in instruction,
            f"Specialist instruction is missing: {phrase!r}",
        )


def main() -> None:
    tests = [
        (test_catalogue_contract, "specialist catalogue contract"),
        (test_seo_wix_product_page_route, "SEO/Wix/CRO routing"),
        (test_aliexpress_uk_product_route, "AliExpress/UK/CRO routing"),
        (test_portuguese_route, "Portuguese routing signals"),
        (
            test_current_query_precedes_conversation_context,
            "current query outranks conversation context",
        ),
        (
            test_follow_up_uses_conversation_context,
            "follow-up uses conversation context",
        ),
        (
            test_default_business_trio,
            "signal-free route uses business defaults",
        ),
        (test_routing_is_deterministic, "routing is deterministic"),
        (
            test_seat_assignment_contract,
            "three unique specialist seats",
        ),
        (
            test_compact_metadata_excludes_scores_and_tracks_degradation,
            "compact degradation metadata",
        ),
        (
            test_specialist_instruction_preserves_evidence_boundaries,
            "specialist evidence boundaries",
        ),
    ]

    for test, label in tests:
        test()
        print(f"PASS  {label}")

    print("\nSpecialist routing tests PASSED.")


if __name__ == "__main__":
    main()
