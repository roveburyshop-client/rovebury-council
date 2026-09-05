"""Deterministic tests for Wix Controlled Access runtime integration.

No real Wix, GitHub, OpenRouter, web or supplier request is made.
"""

from __future__ import annotations

import asyncio
import json
import os

from backend.access import (
    ACCESS_MODE_OPTIONAL,
    CAPABILITY_GITHUB,
    CAPABILITY_WIX,
    AccessProviderRegistry,
)
from backend.access_runtime import (
    build_default_access_registry,
    collect_external_access,
)


FAKE_WIX_KEY = "TEST_WIX_RUNTIME_KEY_MUST_NOT_LEAK"


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


class temporary_env:
    """Small deterministic environment override for one variable."""

    def __init__(
        self,
        name: str,
        value: str | None,
    ) -> None:
        self.name = name
        self.value = value
        self.had_original = False
        self.original = None

    def __enter__(
        self,
    ):
        self.had_original = (
            self.name in os.environ
        )
        self.original = os.environ.get(
            self.name
        )

        if self.value is None:
            os.environ.pop(
                self.name,
                None,
            )
        else:
            os.environ[
                self.name
            ] = self.value

        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        if self.had_original:
            assert self.original is not None
            os.environ[
                self.name
            ] = self.original
        else:
            os.environ.pop(
                self.name,
                None,
            )


def test_default_registry_keeps_github_when_wix_key_missing() -> None:
    with temporary_env(
        "ROVEBURY_WIX_API_KEY",
        None,
    ):
        registry = (
            build_default_access_registry()
        )

    capabilities = (
        registry.registered_capabilities
    )

    require(
        CAPABILITY_GITHUB
        in capabilities,
        (
            "Missing Wix configuration removed the existing "
            f"GitHub provider: {capabilities!r}"
        ),
    )
    require(
        CAPABILITY_WIX
        not in capabilities,
        (
            "Wix provider registered without a backend API key: "
            f"{capabilities!r}"
        ),
    )


def test_default_registry_registers_wix_when_key_present() -> None:
    with temporary_env(
        "ROVEBURY_WIX_API_KEY",
        FAKE_WIX_KEY,
    ):
        registry = (
            build_default_access_registry()
        )

    capabilities = (
        registry.registered_capabilities
    )

    require(
        CAPABILITY_GITHUB
        in capabilities,
        (
            "Wix registration displaced the GitHub provider: "
            f"{capabilities!r}"
        ),
    )
    require(
        CAPABILITY_WIX
        in capabilities,
        (
            "Configured Wix provider was not registered: "
            f"{capabilities!r}"
        ),
    )


async def test_required_wix_access_executes_raw_query_only() -> None:
    registry = AccessProviderRegistry()
    calls = []

    async def wix_provider(
        request,
    ):
        calls.append(
            dict(request)
        )
        return [
            {
                "source_name": (
                    "Wix Stores fixture"
                ),
                "locator": (
                    "https://www.rovebury.com/"
                    "product-page/fixture"
                ),
                "observed_at": (
                    "2026-09-05T03:30:00Z"
                ),
                "content": (
                    "Product: Runtime Fixture\n"
                    "Current price: £42.00\n"
                    "Availability: IN_STOCK"
                ),
            }
        ]

    registry.register(
        CAPABILITY_WIX,
        wix_provider,
    )

    raw_query = (
        "Check my Wix for the current product price."
    )
    private_context = (
        "[User message]\n"
        "PRIVATE_CONTEXT_MUST_NOT_REACH_WIX"
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
                "capability": CAPABILITY_WIX,
                "query": raw_query,
                "router_version": (
                    "access-rules-v1"
                ),
            }
        ],
        (
            "Wix runtime provider boundary changed: "
            f"{calls!r}"
        ),
    )
    require(
        (
            "PRIVATE_CONTEXT_MUST_NOT_REACH_WIX"
            not in json.dumps(
                calls
            )
        ),
        (
            "Conversation context leaked into "
            "the Wix provider request."
        ),
    )
    require(
        "Current price: £42.00"
        in access_context,
        (
            "Wix live evidence did not reach "
            f"controlled access context: {access_context!r}"
        ),
    )
    require(
        metadata["executed"]
        is True,
        (
            "Required Wix access was not "
            f"executed: {metadata!r}"
        ),
    )
    require(
        metadata[
            "executed_capabilities"
        ]
        == [CAPABILITY_WIX],
        (
            "Executed Wix capability was not "
            f"recorded correctly: {metadata!r}"
        ),
    )
    require(
        metadata["degraded"]
        is False,
        (
            "Successful Wix access was incorrectly "
            f"degraded: {metadata!r}"
        ),
    )
    require(
        '"content"'
        not in json.dumps(
            metadata
        ),
        (
            "Wix evidence body leaked into "
            f"compact metadata: {metadata!r}"
        ),
    )


async def test_optional_wix_reference_does_not_execute() -> None:
    registry = AccessProviderRegistry()
    calls = []

    async def wix_provider(
        request,
    ):
        calls.append(
            dict(request)
        )
        return []

    registry.register(
        CAPABILITY_WIX,
        wix_provider,
    )

    access_context, metadata = (
        await collect_external_access(
            "Wix Stores catalog",
            "",
            registry=registry,
        )
    )

    require(
        metadata["mode"]
        == ACCESS_MODE_OPTIONAL,
        (
            "Plain Wix domain reference did not remain optional: "
            f"{metadata!r}"
        ),
    )
    require(
        calls == [],
        (
            "Optional Wix access executed automatically: "
            f"{calls!r}"
        ),
    )
    require(
        metadata["executed"]
        is False,
        (
            "Optional Wix access was marked executed: "
            f"{metadata!r}"
        ),
    )
    require(
        access_context == "",
        (
            "Optional Wix access unexpectedly produced "
            f"model-facing access context: {access_context!r}"
        ),
    )


async def test_missing_wix_key_degrades_without_breaking_registry() -> None:
    with temporary_env(
        "ROVEBURY_WIX_API_KEY",
        None,
    ):
        access_context, metadata = (
            await collect_external_access(
                (
                    "Check my Wix for the current "
                    "product price."
                ),
                "",
            )
        )

    require(
        metadata[
            "requested_capabilities"
        ]
        == [CAPABILITY_WIX],
        (
            "Planner no longer selected Wix: "
            f"{metadata!r}"
        ),
    )
    require(
        metadata["executed"]
        is False,
        (
            "Missing Wix credential was incorrectly "
            f"marked executed: {metadata!r}"
        ),
    )
    require(
        CAPABILITY_WIX
        in metadata[
            "missing_capabilities"
        ],
        (
            "Missing Wix provider was not surfaced "
            f"as degraded access: {metadata!r}"
        ),
    )
    require(
        metadata["degraded"]
        is True,
        (
            "Missing Wix provider did not degrade "
            f"the access result: {metadata!r}"
        ),
    )
    require(
        (
            "No usable live external evidence "
            "was obtained."
        )
        in access_context,
        (
            "Anti-fabrication access context was "
            f"not emitted: {access_context!r}"
        ),
    )
    require(
        FAKE_WIX_KEY
        not in json.dumps(
            metadata
        ),
        (
            "Test Wix credential leaked into "
            f"metadata: {metadata!r}"
        ),
    )


async def main() -> None:
    test_default_registry_keeps_github_when_wix_key_missing()
    print(
        "PASS  missing Wix key keeps GitHub registry healthy"
    )

    test_default_registry_registers_wix_when_key_present()
    print(
        "PASS  configured Wix key registers read-only Wix provider"
    )

    await test_required_wix_access_executes_raw_query_only()
    print(
        "PASS  required Wix access executes through raw-query boundary"
    )

    await test_optional_wix_reference_does_not_execute()
    print(
        "PASS  optional Wix access is planned but not autoexecuted"
    )

    await test_missing_wix_key_degrades_without_breaking_registry()
    print(
        "PASS  missing Wix key degrades safely without fabrication"
    )

    print(
        "\nWix Controlled Access runtime integration tests PASSED."
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
