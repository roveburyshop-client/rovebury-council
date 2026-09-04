"""API + streaming + persistence smoke test for the ROVEBURY Council."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx

from backend import storage
from backend.main import app


QUERY = (
    "For ROVEBURY, what are our primary market, ecommerce platform, "
    "primary supplier marketplace, store currency, and customer-facing "
    "language? Use the internal ROVEBURY knowledge."
)

REQUIRED_SOURCES = {
    "decisions/DEC-001-united-kingdom-primary-market.md",
    "memory/entities/brand-rovebury.md",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def collect_sse_events(
    client: httpx.AsyncClient,
    conversation_id: str,
) -> list[dict]:
    events: list[dict] = []

    async with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/message/stream",
        json={"content": QUERY},
    ) as response:
        require(
            response.status_code == 200,
            f"Streaming endpoint returned HTTP {response.status_code}.",
        )

        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue

            payload = line[6:]
            event = json.loads(payload)
            events.append(event)

    return events


async def main() -> None:
    original_data_dir = storage.DATA_DIR

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage.DATA_DIR = temp_dir

            transport = httpx.ASGITransport(app=app)

            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                timeout=180.0,
            ) as client:
                print("Running ROVEBURY API streaming smoke test...\n")

                health = await client.get("/")
                require(
                    health.status_code == 200,
                    "Health endpoint failed.",
                )
                require(
                    health.json().get("status") == "ok",
                    "Health endpoint did not return status=ok.",
                )
                print("PASS  FastAPI health endpoint")

                created = await client.post(
                    "/api/conversations",
                    json={},
                )
                require(
                    created.status_code == 200,
                    "Conversation creation failed.",
                )

                conversation = created.json()
                conversation_id = conversation["id"]

                print(
                    "PASS  conversation created "
                    f"({conversation_id})"
                )

                events = await collect_sse_events(
                    client,
                    conversation_id,
                )

                event_types = [
                    event.get("type")
                    for event in events
                ]

                print("\n=== SSE EVENTS ===")
                for event_type in event_types:
                    print(f"  - {event_type}")

                required_event_types = {
                    "stage1_start",
                    "stage1_complete",
                    "stage2_start",
                    "stage2_complete",
                    "stage3_start",
                    "stage3_complete",
                    "complete",
                }

                missing_events = sorted(
                    required_event_types - set(event_types)
                )
                require(
                    not missing_events,
                    "Missing SSE events: "
                    + ", ".join(missing_events),
                )

                error_events = [
                    event
                    for event in events
                    if event.get("type") == "error"
                ]
                require(
                    not error_events,
                    "Streaming endpoint emitted an error event: "
                    + repr(error_events),
                )

                print("PASS  streaming lifecycle completed")

                stage2_event = next(
                    event
                    for event in events
                    if event.get("type") == "stage2_complete"
                )

                metadata = stage2_event.get("metadata", {})
                knowledge = metadata.get("knowledge", {})
                sources = knowledge.get("sources", [])

                require(
                    knowledge.get("used") is True,
                    "Streaming metadata says memory was not used.",
                )
                require(
                    knowledge.get("characters", 0) > 0,
                    "Streaming metadata has empty knowledge context.",
                )

                missing_sources = sorted(
                    REQUIRED_SOURCES - set(sources)
                )
                require(
                    not missing_sources,
                    "Streaming metadata is missing canonical sources: "
                    + ", ".join(missing_sources),
                )

                print("\n=== STREAMING MEMORY METADATA ===")
                print(f"Used:       {knowledge.get('used')}")
                print(
                    "Characters: "
                    f"{knowledge.get('characters')}"
                )
                print(f"Sources:    {len(sources)}")
                for source in sources:
                    print(f"  - {source}")

                print(
                    "PASS  streaming metadata contains governed memory"
                )

                reloaded = await client.get(
                    f"/api/conversations/{conversation_id}"
                )
                require(
                    reloaded.status_code == 200,
                    "Conversation reload failed.",
                )

                saved_conversation = reloaded.json()
                messages = saved_conversation.get(
                    "messages",
                    [],
                )

                require(
                    len(messages) == 2,
                    "Expected one user message and one assistant message "
                    f"after reload; got {len(messages)}.",
                )

                require(
                    messages[0].get("role") == "user",
                    "First persisted message is not the user message.",
                )
                require(
                    messages[1].get("role") == "assistant",
                    "Second persisted message is not the assistant message.",
                )

                saved_metadata = messages[1].get(
                    "metadata",
                    {},
                )
                saved_knowledge = saved_metadata.get(
                    "knowledge",
                    {},
                )

                require(
                    saved_knowledge == knowledge,
                    "Persisted knowledge metadata differs from "
                    "the metadata emitted by streaming.",
                )

                stage3 = messages[1].get(
                    "stage3",
                    {},
                )
                require(
                    stage3.get("response", "").strip(),
                    "Persisted Chairman response is empty.",
                )

                print("PASS  assistant response persisted")
                print(
                    "PASS  knowledge metadata survived conversation reload"
                )

                title = saved_conversation.get(
                    "title",
                    "",
                )
                require(
                    bool(title),
                    "Conversation title is empty after streaming.",
                )

                print(f"PASS  conversation title persisted: {title}")

                persisted_files = list(
                    Path(temp_dir).glob("*.json")
                )
                require(
                    len(persisted_files) == 1,
                    "Expected exactly one temporary conversation JSON file.",
                )

                print(
                    "PASS  storage wrote exactly one conversation file"
                )

                print(
                    "\nAPI streaming + persistence smoke test PASSED."
                )

    finally:
        storage.DATA_DIR = original_data_dir


if __name__ == "__main__":
    asyncio.run(main())
