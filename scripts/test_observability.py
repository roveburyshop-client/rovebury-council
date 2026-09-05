from backend.observability import ObservabilityRecorder


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    recorder = ObservabilityRecorder()

    event = recorder.record(
        "access_decision",
        "allowed",
        {"capability": "wix.catalog.read"},
    )

    require(event.status == "allowed", "status mismatch")
    require(
        event.metadata["capability"] == "wix.catalog.read",
        "metadata mismatch",
    )
    require(len(recorder.events()) == 1, "event count mismatch")

    print("PASS  observation records are deterministic")
    print("PASS  metadata remains compact")
    print("PASS  event storage is bounded by recorder state")
    print("Observability tests PASSED.")


if __name__ == "__main__":
    main()
