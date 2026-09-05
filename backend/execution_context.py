from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class ExecutionContext:
    execution_id: str
    request_id: str
    capability: str
    actor: str
    metadata: dict

    @classmethod
    def create(
        cls,
        request_id: str,
        capability: str,
        actor: str,
        metadata: dict | None = None,
    ):
        return cls(
            execution_id=str(uuid4()),
            request_id=request_id,
            capability=capability,
            actor=actor,
            metadata=metadata or {},
        )
