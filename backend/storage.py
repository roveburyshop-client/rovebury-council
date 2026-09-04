"""JSON-based storage for conversations."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import DATA_DIR


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(
        parents=True,
        exist_ok=True,
    )


def get_conversation_path(
    conversation_id: str
) -> str:
    """Get the file path for a conversation."""
    return os.path.join(
        DATA_DIR,
        f"{conversation_id}.json",
    )


def create_conversation(
    conversation_id: str
) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        New conversation dict
    """
    ensure_data_dir()

    conversation = {
        "id": conversation_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": "New Conversation",
        "messages": [],
    }

    path = get_conversation_path(
        conversation_id
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            conversation,
            file,
            indent=2,
            ensure_ascii=False,
        )

    return conversation


def get_conversation(
    conversation_id: str
) -> Optional[Dict[str, Any]]:
    """
    Load a conversation from storage.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Conversation dict or None if not found
    """
    path = get_conversation_path(
        conversation_id
    )

    if not os.path.exists(path):
        return None

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_conversation(
    conversation: Dict[str, Any]
):
    """
    Save a conversation.

    Args:
        conversation: Conversation dict to save
    """
    ensure_data_dir()

    path = get_conversation_path(
        conversation["id"]
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            conversation,
            file,
            indent=2,
            ensure_ascii=False,
        )


def list_conversations() -> List[Dict[str, Any]]:
    """
    List all conversations (metadata only).

    Returns:
        List of conversation metadata dicts
    """
    ensure_data_dir()

    conversations = []

    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue

        path = os.path.join(
            DATA_DIR,
            filename,
        )

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        conversations.append(
            {
                "id": data["id"],
                "created_at": data["created_at"],
                "title": data.get(
                    "title",
                    "New Conversation",
                ),
                "message_count": len(
                    data["messages"]
                ),
            }
        )

    conversations.sort(
        key=lambda item: item["created_at"],
        reverse=True,
    )

    return conversations


def add_user_message(
    conversation_id: str,
    content: str,
):
    """
    Add a user message to a conversation.

    Args:
        conversation_id: Conversation identifier
        content: User message content
    """
    conversation = get_conversation(
        conversation_id
    )

    if conversation is None:
        raise ValueError(
            f"Conversation {conversation_id} not found"
        )

    conversation["messages"].append(
        {
            "role": "user",
            "content": content,
        }
    )

    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Add an assistant message with all Council stages.

    Metadata may include:
    - anonymous-label mappings
    - aggregate rankings
    - knowledge retrieval information

    Existing callers that do not provide metadata remain supported.
    """
    conversation = get_conversation(
        conversation_id
    )

    if conversation is None:
        raise ValueError(
            f"Conversation {conversation_id} not found"
        )

    assistant_message = {
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
    }

    if metadata is not None:
        assistant_message["metadata"] = metadata

    conversation["messages"].append(
        assistant_message
    )

    save_conversation(conversation)


def update_conversation_title(
    conversation_id: str,
    title: str,
):
    """
    Update the title of a conversation.

    Args:
        conversation_id: Conversation identifier
        title: New title for the conversation
    """
    conversation = get_conversation(
        conversation_id
    )

    if conversation is None:
        raise ValueError(
            f"Conversation {conversation_id} not found"
        )

    conversation["title"] = title

    save_conversation(conversation)