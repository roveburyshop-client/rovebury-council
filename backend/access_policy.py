from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    capability: str
    decision: str
    reason: str


class AccessPolicyEngine:
    def __init__(self, registry):
        self.registry = registry

    def evaluate(self, capability: str) -> PolicyDecision:
        entry = self.registry.get(capability)

        if entry is None:
            return PolicyDecision(
                capability=capability,
                decision="denied",
                reason="unknown_capability",
            )

        return PolicyDecision(
            capability=capability,
            decision="allowed",
            reason="registered_capability",
        )
