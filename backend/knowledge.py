"""Read-only, trust-aware access to the ROVEBURY knowledge base."""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import re
from typing import Any


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "what",
    "which",
    "who",
    "how",
    "does",
    "should",
    "can",
    "could",
    "would",
    "will",
    "its",
    "our",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "use",
    "uses",
    "using",
    "about",
}

PROJECTS_DIR = Path(__file__).resolve().parents[2]
DEFAULT_KNOWLEDGE_DIR = PROJECTS_DIR / "rovebury-knowledge"
KNOWLEDGE_DIR = Path(
    os.getenv("ROVEBURY_KNOWLEDGE_DIR", str(DEFAULT_KNOWLEDGE_DIR))
).expanduser()

EXCLUDED_DIRECTORIES = {
    ".git",
    "inbox",
    "templates",
}

EXCLUDED_FILENAMES = {
    "README.md",
}

RELEVANCE_THRESHOLD = 2

ELIGIBLE_STATUSES = {"active"}
ELIGIBLE_AUTHORITIES = {"A1", "A2", "A3", "A4"}

AUTHORITY_WEIGHTS = {
    "A1": 0.40,
    "A2": 0.30,
    "A3": 0.20,
    "A4": 0.10,
}

VERIFICATION_WEIGHTS = {
    "founder_confirmed": 0.20,
    "internally_verified": 0.20,
    "externally_verified": 0.20,
    "partially_verified": 0.08,
    "unverified": 0.00,
}

CONFIDENCE_WEIGHTS = {
    "high": 0.10,
    "medium": 0.05,
    "low": 0.00,
}

STABLE_FRESHNESS_BONUS = 0.05
CURRENT_TIME_SENSITIVE_BONUS = 0.05
STALE_TIME_SENSITIVE_PENALTY = -0.20


def get_knowledge_dir() -> Path:
    """Return the configured location of the private knowledge repository."""
    return KNOWLEDGE_DIR


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """
    Parse the simple scalar YAML frontmatter used by the ROVEBURY knowledge base.

    This intentionally avoids adding a YAML dependency. The governed metadata
    currently uses one `key: value` pair per line.
    """
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        return {}, text

    closing_index = None

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break

    if closing_index is None:
        return {}, text

    metadata: dict[str, str] = {}

    for raw_line in lines[1:closing_index]:
        line = raw_line.strip()

        if not line or line.startswith("#") or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if key:
            metadata[key] = value

    body = "\n".join(lines[closing_index + 1 :]).strip()
    return metadata, body


def load_knowledge_documents() -> list[dict[str, Any]]:
    """Load governed Markdown documents from the private knowledge repository."""
    if not KNOWLEDGE_DIR.exists():
        raise FileNotFoundError(
            f"ROVEBURY knowledge base was not found at: {KNOWLEDGE_DIR}"
        )

    documents: list[dict[str, Any]] = []

    for path in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        relative_path = path.relative_to(KNOWLEDGE_DIR)

        if any(part in EXCLUDED_DIRECTORIES for part in relative_path.parts):
            continue

        if path.name in EXCLUDED_FILENAMES:
            continue

        content = path.read_text(encoding="utf-8-sig")
        metadata, body = _parse_frontmatter(content)

        documents.append(
            {
                "path": relative_path.as_posix(),
                "content": content,
                "body": body,
                "metadata": metadata,
            }
        )

    return documents


def _tokenize(text: str) -> set[str]:
    """Convert text into normalized search tokens."""
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _is_retrieval_eligible(document: dict[str, Any]) -> bool:
    """
    Apply the governance eligibility gate.

    Normal retrieval is fail-closed:
    - only active documents are eligible;
    - A1-A4 are eligible;
    - A5, draft, superseded, deprecated or malformed documents are excluded.
    """
    metadata = document.get("metadata") or {}

    return (
        metadata.get("status") in ELIGIBLE_STATUSES
        and metadata.get("authority") in ELIGIBLE_AUTHORITIES
    )


def _calculate_relevance(query_tokens: set[str], document: dict[str, Any]) -> int:
    """
    Calculate lexical relevance without indexing frontmatter metadata.

    Path matches keep the existing 3x weight. Body matches use the actual
    Markdown body only, preventing governance terms such as `A1`, `active`,
    `high`, or `founder_confirmed` from polluting relevance.
    """
    path_tokens = _tokenize(document["path"])
    body_tokens = _tokenize(document["body"])

    path_matches = len(query_tokens & path_tokens)
    body_matches = len(query_tokens & body_tokens)

    return (path_matches * 3) + body_matches


def _parse_iso_date(value: str | None) -> date | None:
    if not value or value.lower() == "null":
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _calculate_freshness_modifier(
    metadata: dict[str, str],
    *,
    today: date | None = None,
) -> float:
    freshness = metadata.get("freshness")

    if freshness == "stable":
        return STABLE_FRESHNESS_BONUS

    if freshness != "time_sensitive":
        return 0.0

    review_after = _parse_iso_date(metadata.get("review_after"))

    if review_after is None:
        return 0.0

    current_date = today or date.today()

    if review_after < current_date:
        return STALE_TIME_SENSITIVE_PENALTY

    return CURRENT_TIME_SENSITIVE_BONUS


def _calculate_trust_modifier(
    document: dict[str, Any],
    *,
    today: date | None = None,
) -> float:
    """
    Calculate a bounded trust modifier.

    The maximum positive modifier is less than 1.0. Relevance scores are
    integers, so one full point of relevance always beats any trust advantage.
    Trust therefore refines ranking among similarly relevant documents instead
    of allowing an unrelated high-authority document to dominate.
    """
    metadata = document.get("metadata") or {}

    modifier = 0.0
    modifier += AUTHORITY_WEIGHTS.get(metadata.get("authority", ""), 0.0)
    modifier += VERIFICATION_WEIGHTS.get(
        metadata.get("verification", ""),
        0.0,
    )
    modifier += CONFIDENCE_WEIGHTS.get(
        metadata.get("confidence", ""),
        0.0,
    )
    modifier += _calculate_freshness_modifier(metadata, today=today)

    return round(modifier, 4)


def rank_knowledge_documents(
    query: str,
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """
    Return eligible relevant documents in deterministic trust-aware order.

    Each result contains:
    - document
    - relevance_score
    - trust_modifier
    - final_score
    """
    documents = load_knowledge_documents()
    query_tokens = _tokenize(query)

    if not query_tokens:
        return []

    ranked: list[dict[str, Any]] = []

    for document in documents:
        if not _is_retrieval_eligible(document):
            continue

        relevance_score = _calculate_relevance(query_tokens, document)

        if relevance_score < RELEVANCE_THRESHOLD:
            continue

        trust_modifier = _calculate_trust_modifier(
            document,
            today=today,
        )
        final_score = relevance_score + trust_modifier

        ranked.append(
            {
                "document": document,
                "relevance_score": relevance_score,
                "trust_modifier": trust_modifier,
                "final_score": final_score,
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["final_score"],
            -item["relevance_score"],
            -item["trust_modifier"],
            item["document"]["path"],
        )
    )

    return ranked


def retrieve_knowledge(
    query: str,
    max_documents: int = 6,
    max_chars: int = 12000,
) -> str:
    """
    Retrieve a small set of relevant, governed knowledge documents.

    This is deterministic and local. It does not call an LLM, embedding API,
    or external service.
    """
    ranked_documents = rank_knowledge_documents(query)
    selected = ranked_documents[:max_documents]

    context_parts: list[str] = []
    total_chars = 0

    for item in selected:
        document = item["document"]

        block = (
            f"[Knowledge source: {document['path']}]\n"
            f"{document['content'].strip()}"
        )

        if total_chars + len(block) > max_chars:
            break

        context_parts.append(block)
        total_chars += len(block)

    return "\n\n---\n\n".join(context_parts)
