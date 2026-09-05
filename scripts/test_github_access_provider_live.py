"""Real read-only GitHub smoke test for the ROVEBURY public repository.

This test performs exactly one live GitHub REST read through the isolated
provider. It does not invoke OpenRouter or the Council pipeline.
"""

from __future__ import annotations

import asyncio

from backend.access import (
    CAPABILITY_GITHUB,
)
from backend.github_access import (
    DEFAULT_BRANCH,
    DEFAULT_REPOSITORY,
    build_github_read_provider,
)


async def main() -> None:
    print(
        "Running ROVEBURY GitHub provider live smoke test..."
    )
    print(
        f"Repository: {DEFAULT_REPOSITORY}"
    )
    print(
        f"Branch:     {DEFAULT_BRANCH}"
    )

    provider = build_github_read_provider()

    evidence = await provider(
        {
            "capability": CAPABILITY_GITHUB,
            "query": (
                "Check GitHub for the latest commit on branch "
                f"{DEFAULT_BRANCH}."
            ),
            "router_version": "access-rules-v1",
        }
    )

    if not evidence:
        raise AssertionError(
            "GitHub provider returned no live evidence."
        )

    item = evidence[0]

    if "Latest commit:" not in item.get(
        "content",
        "",
    ):
        raise AssertionError(
            f"Unexpected live evidence: {item!r}"
        )

    print(
        "\n=== LIVE GITHUB EVIDENCE ==="
    )
    print(
        item["content"]
    )
    print(
        f"Locator: {item['locator']}"
    )
    print(
        "\nGitHub provider live smoke test PASSED."
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
