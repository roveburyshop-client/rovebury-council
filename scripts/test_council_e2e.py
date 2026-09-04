"""End-to-end smoke test for the ROVEBURY Council + governed memory."""

from __future__ import annotations

import asyncio

from backend.council import run_full_council


QUERY = (
    "For ROVEBURY, what are our primary market, ecommerce platform, "
    "primary supplier marketplace, store currency, and customer-facing "
    "language? Answer from the internal ROVEBURY knowledge available to you. "
    "Do not present internal decisions as independent external evidence."
)

REQUIRED_SOURCES = {
    "decisions/DEC-001-united-kingdom-primary-market.md",
    "memory/entities/brand-rovebury.md",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def main() -> None:
    print("Running ROVEBURY Council end-to-end smoke test...\n")
    print(f"Query: {QUERY}\n")

    stage1, stage2, stage3, metadata = await run_full_council(QUERY)

    knowledge = metadata.get("knowledge", {})
    sources = knowledge.get("sources", [])
    characters = knowledge.get("characters", 0)

    print("=== PIPELINE ===")
    print(f"Stage 1 responses: {len(stage1)}")
    print(f"Stage 2 rankings:  {len(stage2)}")
    print(f"Stage 3 model:     {stage3.get('model')}")
    print()

    print("=== MEMORY ===")
    print(f"Used:       {knowledge.get('used')}")
    print(f"Characters: {characters}")
    print(f"Sources:    {len(sources)}")
    for source in sources:
        print(f"  - {source}")
    print()

    require(
        knowledge.get("used") is True,
        "Expected governed ROVEBURY memory to be used.",
    )
    require(
        characters > 0,
        "Expected non-empty knowledge context.",
    )
    require(
        len(stage1) > 0,
        "Stage 1 returned no model responses.",
    )

    missing_sources = sorted(REQUIRED_SOURCES - set(sources))
    require(
        not missing_sources,
        "Expected canonical sources were not retrieved: "
        + ", ".join(missing_sources),
    )

    final_response = stage3.get("response", "").strip()
    require(
        final_response,
        "Chairman returned an empty final response.",
    )
    require(
        not final_response.startswith("Error:"),
        f"Chairman returned an error response: {final_response}",
    )

    print("=== CHAIRMAN RESPONSE ===")
    print(final_response)
    print()

    print("PASS  governed memory reached the Council")
    print("PASS  canonical ROVEBURY sources were attached")
    print("PASS  Stage 1 produced responses")
    print("PASS  Chairman produced a final response")
    print("\nCouncil end-to-end smoke test PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
