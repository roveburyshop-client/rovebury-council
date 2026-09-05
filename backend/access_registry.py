from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class AccessCapability:
    name: str
    provider: str
    risk: str
    execution_mode: str
    requires_secret: bool
    auto_execute: bool


class AccessRegistry:
    def __init__(self):
        self._capabilities: Dict[str, AccessCapability] = {}

    def register(self, capability: AccessCapability) -> None:
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> Optional[AccessCapability]:
        return self._capabilities.get(name)

    def authorize(self, name: str):
        capability = self.get(name)

        if capability is None:
            return {
                "allowed": False,
                "reason": "unknown_capability",
            }

        return {
            "allowed": True,
            "reason": "registered_capability",
            "provider": capability.provider,
            "execution_mode": capability.execution_mode,
            "auto_execute": capability.auto_execute,
        }


def build_default_registry() -> AccessRegistry:
    registry = AccessRegistry()

    registry.register(
        AccessCapability(
            name="github.read_repository",
            provider="github",
            risk="low",
            execution_mode="bounded_read_only",
            requires_secret=False,
            auto_execute=False,
        )
    )

    registry.register(
        AccessCapability(
            name="wix.catalog.read",
            provider="wix",
            risk="low",
            execution_mode="bounded_read_only",
            requires_secret=True,
            auto_execute=False,
        )
    )

    return registry
