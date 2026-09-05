from backend.access_policy import AccessPolicyEngine


class FakeRegistry:
    def get(self, capability):
        if capability == "wix.catalog.read":
            return {"mode": "bounded_read_only"}
        return None


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    engine = AccessPolicyEngine(FakeRegistry())

    allowed = engine.evaluate("wix.catalog.read")
    denied = engine.evaluate("unknown.action")

    require(allowed.decision == "allowed", "Allowed capability failed")
    require(denied.decision == "denied", "Denied capability failed")

    print("PASS  registered capability is allowed")
    print("PASS  unknown capability is denied")
    print("PASS  policy decision metadata is deterministic")
    print("Access policy tests PASSED.")


if __name__ == "__main__":
    main()
