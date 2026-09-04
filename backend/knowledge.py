"""Read-only access to the ROVEBURY knowledge base."""

from pathlib import Path
import re


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
KNOWLEDGE_DIR = PROJECTS_DIR / "rovebury-knowledge"

EXCLUDED_DIRECTORIES = {
    ".git",
    "inbox",
    "templates",
}

EXCLUDED_FILENAMES = {
    "README.md",
}

CORE_DOCUMENTS = [
    "memory/entities/brand-rovebury.md",
    "decisions/DEC-001-united-kingdom-primary-market.md",
]


def get_knowledge_dir() -> Path:
    """Return the expected location of the private knowledge repository."""
    return KNOWLEDGE_DIR


def load_knowledge_documents() -> list[dict[str, str]]:
    """Load usable Markdown documents from the knowledge repository."""
    if not KNOWLEDGE_DIR.exists():
        raise FileNotFoundError(
            f"ROVEBURY knowledge base was not found at: {KNOWLEDGE_DIR}"
        )

    documents = []

    for path in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        relative_path = path.relative_to(KNOWLEDGE_DIR)

        if any(part in EXCLUDED_DIRECTORIES for part in relative_path.parts):
            continue

        if path.name in EXCLUDED_FILENAMES:
            continue

        documents.append(
            {
                "path": relative_path.as_posix(),
                "content": path.read_text(encoding="utf-8-sig"),
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


def retrieve_knowledge(
    query: str,
    max_documents: int = 6,
    max_chars: int = 12000,
) -> str:
    """
    Retrieve a small set of relevant knowledge documents.

    This is intentionally deterministic and local.
    It does not call an LLM, embedding API, or external service.
    """
    documents = load_knowledge_documents()
    query_tokens = _tokenize(query)

    scored_documents = []

    for document in documents:
        path_tokens = _tokenize(document["path"])
        content_tokens = _tokenize(document["content"])

        path_matches = len(query_tokens & path_tokens)
        content_matches = len(query_tokens & content_tokens)

        score = (path_matches * 3) + content_matches

        if document["path"] in CORE_DOCUMENTS and score > 0:
            score += 2

        if score >= 2:
            scored_documents.append((score, document))

    scored_documents.sort(
        key=lambda item: (-item[0], item[1]["path"])
    )

    selected = scored_documents[:max_documents]

    context_parts = []
    total_chars = 0

    for _, document in selected:
        block = (
            f"[Knowledge source: {document['path']}]\n"
            f"{document['content'].strip()}"
        )

        if total_chars + len(block) > max_chars:
            break

        context_parts.append(block)
        total_chars += len(block)

    return "\n\n---\n\n".join(context_parts)