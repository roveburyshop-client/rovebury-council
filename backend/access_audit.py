from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    capability: str
    decision: str
    reason: str
    execution_mode: str | None = None
    timestamp: str = ""


class AccessAuditLog:
    def __init__(self):
        self._events: List[AuditEvent] = []

    def record(
        self,
        capability: str,
        decision: str,
        reason: str,
        execution_mode: str | None = None,
    ) -> None:
        self._events.append(
            AuditEvent(
                event_type="access_decision",
                capability=capability,
                decision=decision,
                reason=reason,
                execution_mode=execution_mode,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )

    def list_events(self) -> List[Dict[str, Any]]:
        return [asdict(event) for event in self._events]
