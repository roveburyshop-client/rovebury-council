from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    event_type: str
    status: str
    metadata: dict


class ObservabilityRecorder:
    def __init__(self):
        self._events = []

    def record(self, event_type: str, status: str, metadata: dict | None = None):
        event = Observation(
            event_type=event_type,
            status=status,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def events(self):
        return tuple(self._events)
