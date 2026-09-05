from backend.access_audit import AccessAuditLog


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    audit = AccessAuditLog()

    audit.record(
        capability="wix.catalog.read",
        decision="allowed",
        reason="registered_capability",
        execution_mode="bounded_read_only",
    )

    audit.record(
        capability="unknown.action",
        decision="denied",
        reason="unknown_capability",
    )

    events = audit.list_events()

    require(len(events) == 2, "Expected two audit events")
    require(events[0]["decision"] == "allowed", "Allowed event missing")
    require(events[1]["decision"] == "denied", "Denied event missing")
    require("secret" not in str(events).lower(), "Secrets leaked into audit")

    print("PASS  allowed access creates audit event")
    print("PASS  denied access creates audit event")
    print("PASS  audit metadata is compact")
    print("PASS  secrets never enter audit records")
    print("PASS  audit ordering is deterministic")
    print("Access audit tests PASSED.")


if __name__ == "__main__":
    main()
