from backend.access_registry import AccessCapability, AccessRegistry, build_default_registry


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    registry = build_default_registry()

    wix = registry.authorize("wix.catalog.read")
    require(wix["allowed"], "Wix capability should be allowed")

    github = registry.authorize("github.read_repository")
    require(github["allowed"], "GitHub capability should be allowed")

    unknown = registry.authorize("wix.delete_product")
    require(not unknown["allowed"], "Unknown capability should be denied")

    custom = AccessRegistry()
    custom.register(
        AccessCapability(
            name="test.write",
            provider="test",
            risk="high",
            execution_mode="write",
            requires_secret=True,
            auto_execute=False,
        )
    )
    require(
        custom.authorize("test.write")["auto_execute"] is False,
        "Write capability must not auto execute",
    )

    print("PASS  Wix capability registers correctly")
    print("PASS  GitHub capability registers correctly")
    print("PASS  unknown capability denied")
    print("PASS  execution policy metadata preserved")
    print("Access registry tests PASSED.")


if __name__ == "__main__":
    main()
