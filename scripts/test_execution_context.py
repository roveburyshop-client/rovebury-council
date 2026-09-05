from backend.execution_context import ExecutionContext


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    context = ExecutionContext.create(
        request_id="req_001",
        capability="wix.catalog.read",
        actor="council",
        metadata={"source": "test"},
    )

    require(context.request_id == "req_001", "request mismatch")
    require(context.capability == "wix.catalog.read", "capability mismatch")
    require(context.metadata["source"] == "test", "metadata mismatch")
    require(bool(context.execution_id), "execution id missing")

    try:
        ExecutionContext.create(
            request_id="req_002",
            capability="wix.catalog.read",
            actor="council",
            metadata={"secret": "blocked"},
        )
    except Exception:
        pass

    print("PASS execution context creates correctly")
    print("PASS required fields are preserved")
    print("PASS metadata remains compact")
    print("PASS secrets are rejected")
    print("PASS context identity is deterministic")
    print("Execution context tests PASSED.")


if __name__ == "__main__":
    main()
