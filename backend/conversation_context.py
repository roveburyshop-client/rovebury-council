"""Bounded transient conversation context for the ROVEBURY Council."""

from __future__ import annotations

from typing import Any

DEFAULT_MAX_MESSAGES = 8
DEFAULT_MAX_CHARS = 8000
DEFAULT_MAX_MESSAGE_CHARS = 2200


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text

    marker = "\n[truncated]"
    if max_chars <= len(marker):
        return text[:max_chars]

    return text[: max_chars - len(marker)].rstrip() + marker


def _message_block(
    message: dict[str, Any],
    *,
    max_message_chars: int,
) -> str:
    role = message.get("role")

    if role == "user":
        text = _clean_text(message.get("content"))
        if not text:
            return ""
        return "[User message]\n" + _truncate(text, max_message_chars)

    if role == "assistant":
        stage3 = message.get("stage3")
        if not isinstance(stage3, dict):
            return ""

        text = _clean_text(stage3.get("response"))
        if not text:
            return ""

        return (
            "[Assistant final answer]\n"
            + _truncate(text, max_message_chars)
        )

    return ""


def build_conversation_context(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = DEFAULT_MAX_MESSAGES,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_message_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
) -> str:
    """Build recent transient context from persisted conversation messages.

    Only user messages and final Stage 3 answers are included. Stage 1 drafts,
    Stage 2 rankings, and metadata are excluded. Newer messages are prioritised
    when the character budget is reached.
    """
    if max_messages <= 0 or max_chars <= 0 or max_message_chars <= 0:
        return ""

    blocks = []
    for message in messages:
        block = _message_block(
            message,
            max_message_chars=max_message_chars,
        )
        if block:
            blocks.append(block)

    if not blocks:
        return ""

    blocks = blocks[-max_messages:]
    separator = "\n\n---\n\n"
    selected_reversed: list[str] = []
    used = 0

    for block in reversed(blocks):
        separator_cost = len(separator) if selected_reversed else 0
        remaining = max_chars - used - separator_cost

        if remaining <= 0:
            break

        if len(block) > remaining:
            if remaining < 80:
                break
            block = _truncate(block, remaining)

        selected_reversed.append(block)
        used += len(block) + separator_cost

    return separator.join(reversed(selected_reversed))


def build_contextual_query(
    user_query: str,
    conversation_context: str,
) -> str:
    """Combine the current question with transient recent context."""
    if not conversation_context:
        return user_query

    return f"""Use the recent conversation context below only to understand continuity and resolve references in the current user question.

CONVERSATION CONTEXT RULES:
- This is transient conversation history, not canonical ROVEBURY knowledge.
- Temporary values from prior turns stay temporary and must not become persistent ROVEBURY facts.
- Previous assistant answers are prior model output, not independent evidence.
- The current user question takes precedence over conflicting earlier conversational instructions.
- Use governed ROVEBURY knowledge supplied separately by the Council when it conflicts with conversation-level speculation about company facts.

<RECENT_CONVERSATION_CONTEXT>
{conversation_context}
</RECENT_CONVERSATION_CONTEXT>

CURRENT USER QUESTION:
{user_query}"""
