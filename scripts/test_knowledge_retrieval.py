"""Deterministic tests for ROVEBURY trust-aware knowledge retrieval."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile

import backend.knowledge as knowledge


def write_doc(
    root: Path,
    relative_path: str,
    *,
    status: str = "active",
    authority: str = "A3",
    verification: str = "externally_verified",
    confidence: str = "high",
    freshness: str = "stable",
    body: str,
    review_after: str | None = None,
) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)

    optional_review = (
        f"review_after: {review_after}\n"
        if review_after is not None
        else ""
    )

    content = (
        "---\n"
        f"id: {path.stem}\n"
        "type: research\n"
        f"status: {status}\n"
        f"authority: {authority}\n"
        f"verification: {verification}\n"
        f"confidence: {confidence}\n"
        f"freshness: {freshness}\n"
        "created: 2026-09-04\n"
        "updated: 2026-09-04\n"
        "last_verified: 2026-09-04\n"
        f"{optional_review}"
        "---\n\n"
        f"# Test Document\n\n{body}\n"
    )

    path.write_text(content, encoding="utf-8")


def ranked_paths(query: str, *, today: date | None = None) -> list[str]:
    return [
        item["document"]["path"]
        for item in knowledge.rank_knowledge_documents(
            query,
            today=today,
        )
    ]


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected!r}\nActual:   {actual!r}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_synthetic_tests() -> None:
    original_dir = knowledge.KNOWLEDGE_DIR

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            knowledge.KNOWLEDGE_DIR = root

            # Same relevance: higher authority should win.
            write_doc(
                root,
                "research/a1-strategy.md",
                authority="A1",
                verification="founder_confirmed",
                body="pricing strategy",
            )
            write_doc(
                root,
                "research/a3-strategy.md",
                authority="A3",
                verification="externally_verified",
                body="pricing strategy",
            )

            paths = ranked_paths("pricing strategy")
            assert_equal(
                paths[:2],
                [
                    "research/a1-strategy.md",
                    "research/a3-strategy.md",
                ],
                "A1 should outrank A3 when lexical relevance is equal.",
            )

            # Stronger relevance must beat higher authority.
            write_doc(
                root,
                "research/high-authority-weak-match.md",
                authority="A1",
                verification="founder_confirmed",
                body="underseat",
            )
            write_doc(
                root,
                "research/verified-strong-match.md",
                authority="A3",
                verification="externally_verified",
                body="underseat backpack cabin dimensions",
            )

            paths = ranked_paths(
                "underseat backpack cabin dimensions"
            )
            assert_equal(
                paths[0],
                "research/verified-strong-match.md",
                "A more relevant A3 document must beat a less relevant A1 document.",
            )

            # Inactive documents must never be retrieved.
            write_doc(
                root,
                "research/superseded.md",
                status="superseded",
                authority="A1",
                verification="founder_confirmed",
                body="unique superseded keyword",
            )

            paths = ranked_paths("unique superseded keyword")
            assert_true(
                "research/superseded.md" not in paths,
                "Superseded documents must be excluded.",
            )

            # A5 is outside normal retrieval.
            write_doc(
                root,
                "research/unverified-a5.md",
                authority="A5",
                verification="unverified",
                confidence="low",
                body="unique unverified supplier claim",
            )

            paths = ranked_paths("unique unverified supplier claim")
            assert_true(
                "research/unverified-a5.md" not in paths,
                "A5 documents must be excluded from normal retrieval.",
            )

            # Frontmatter metadata must not create lexical relevance.
            write_doc(
                root,
                "research/frontmatter-only.md",
                authority="A2",
                verification="founder_confirmed",
                body="completely unrelated body",
            )

            paths = ranked_paths("founder confirmed")
            assert_true(
                "research/frontmatter-only.md" not in paths,
                "Frontmatter metadata must not be indexed as body relevance.",
            )

            # An expired time-sensitive review date should lower trust.
            write_doc(
                root,
                "research/current-price.md",
                authority="A3",
                verification="externally_verified",
                freshness="time_sensitive",
                review_after="2026-12-01",
                body="competitor cabin bag price",
            )
            write_doc(
                root,
                "research/stale-price.md",
                authority="A3",
                verification="externally_verified",
                freshness="time_sensitive",
                review_after="2026-01-01",
                body="competitor cabin bag price",
            )

            paths = ranked_paths(
                "competitor cabin bag price",
                today=date(2026, 9, 4),
            )
            current_index = paths.index(
                "research/current-price.md"
            )
            stale_index = paths.index(
                "research/stale-price.md"
            )
            assert_true(
                current_index < stale_index,
                "Current time-sensitive evidence should outrank stale evidence.",
            )

    finally:
        knowledge.KNOWLEDGE_DIR = original_dir


def run_real_knowledge_smoke_test() -> None:
    knowledge_dir = knowledge.get_knowledge_dir()

    if not knowledge_dir.exists():
        print(
            "SKIP  real knowledge smoke test "
            f"(not found at {knowledge_dir})"
        )
        return

    ranked = knowledge.rank_knowledge_documents(
        "What are ROVEBURY's primary market and ecommerce platform?"
    )
    paths = [item["document"]["path"] for item in ranked]

    assert_true(
        "memory/entities/brand-rovebury.md" in paths,
        "Real KB should retrieve the canonical ROVEBURY brand entity.",
    )
    assert_true(
        "memory/entities/platform-wix.md" in paths,
        "Real KB should retrieve the Wix platform entity.",
    )

    print("PASS  real knowledge smoke test")

    print("\nTop real-KB ranking:")
    for index, item in enumerate(ranked[:6], start=1):
        document = item["document"]
        metadata = document["metadata"]
        print(
            f"{index}. {document['path']} | "
            f"relevance={item['relevance_score']} | "
            f"trust={item['trust_modifier']:.2f} | "
            f"final={item['final_score']:.2f} | "
            f"authority={metadata.get('authority')}"
        )


def main() -> None:
    run_synthetic_tests()
    print("PASS  synthetic trust-aware retrieval tests")

    run_real_knowledge_smoke_test()

    print("\nAll trust-aware retrieval tests PASSED.")


if __name__ == "__main__":
    main()
