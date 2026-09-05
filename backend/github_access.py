"""Read-only GitHub access provider for the ROVEBURY Council.

This adapter implements the allowlisted ``github`` capability from
``backend.access``. It is intentionally narrow:

- read-only HTTP GET requests only;
- fixed ``api.github.com`` base URL;
- fixed configured repository (the user query cannot choose another repo);
- bounded response summaries rather than raw API payload persistence;
- optional token from environment, never required for public repositories;
- no LLM calls and no Council orchestration changes.

Phase 5A.2 keeps this provider isolated from the live Council pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
from typing import Any
from urllib.parse import quote

import httpx

from .access import CAPABILITY_GITHUB


GITHUB_API_BASE = "https://api.github.com"
DEFAULT_REPOSITORY = os.getenv(
    "ROVEBURY_GITHUB_REPOSITORY",
    "roveburyshop-client/rovebury-council",
)
DEFAULT_BRANCH = os.getenv(
    "ROVEBURY_GITHUB_BRANCH",
    "rovebury-dev",
)
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_COMMIT_MESSAGE_CHARS = 600

_REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)
_REF_RE = re.compile(
    r"^[A-Za-z0-9._/-]{1,200}$"
)
_SHA_RE = re.compile(
    r"\b[0-9a-fA-F]{7,40}\b"
)


@dataclass(frozen=True)
class GitHubReadIntent:
    """Deterministic read intent derived from the raw current query."""

    kind: str
    ref: str | None = None
    commit_sha: str | None = None


def _normalise_space(value: str) -> str:
    return " ".join(
        (value or "").strip().split()
    )


def _safe_repository(
    repository_full_name: str,
) -> str:
    repository = _normalise_space(
        repository_full_name
    )

    if not _REPOSITORY_RE.fullmatch(
        repository
    ):
        raise ValueError(
            "repository_full_name must be in owner/name format"
        )

    return repository


def _safe_ref(
    value: str | None,
    fallback: str,
) -> str:
    candidate = _normalise_space(
        value or fallback
    )

    if not _REF_RE.fullmatch(
        candidate
    ):
        return fallback

    return candidate


def parse_github_read_intent(
    query: str,
    default_branch: str = DEFAULT_BRANCH,
) -> GitHubReadIntent:
    """Parse a small read-only GitHub intent without model assistance."""
    text = _normalise_space(query)
    lowered = text.lower()

    sha_match = _SHA_RE.search(
        text
    )

    if (
        sha_match
        and (
            "commit" in lowered
            or "sha" in lowered
        )
        and "latest commit" not in lowered
        and "ultimo commit" not in lowered
        and "último commit" not in lowered
    ):
        return GitHubReadIntent(
            kind="commit",
            commit_sha=sha_match.group(0),
        )

    branch_patterns = (
        r"\bbranch\s+([A-Za-z0-9._/-]{1,200})",
        r"\bramo\s+([A-Za-z0-9._/-]{1,200})",
    )

    branch = None

    for pattern in branch_patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            branch = match.group(1).rstrip(
                ".,;:!?"
            )
            break

    branch = _safe_ref(
        branch,
        default_branch,
    )

    if any(
        phrase in lowered
        for phrase in (
            "latest commit",
            "most recent commit",
            "ultimo commit",
            "último commit",
            "commit mais recente",
            "recent commit",
        )
    ):
        return GitHubReadIntent(
            kind="latest_commit",
            ref=branch,
        )

    if any(
        phrase in lowered
        for phrase in (
            "branch",
            "ramo",
            "rovebury-dev",
        )
    ):
        return GitHubReadIntent(
            kind="branch",
            ref=branch,
        )

    return GitHubReadIntent(
        kind="repository",
    )


class GitHubReadProvider:
    """Callable read-only provider for the ``github`` capability."""

    def __init__(
        self,
        repository_full_name: str = DEFAULT_REPOSITORY,
        default_branch: str = DEFAULT_BRANCH,
        *,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.repository_full_name = (
            _safe_repository(
                repository_full_name
            )
        )
        self.default_branch = _safe_ref(
            default_branch,
            DEFAULT_BRANCH,
        )
        self.token = (
            token
            if token is not None
            else os.getenv(
                "ROVEBURY_GITHUB_TOKEN"
            )
            or os.getenv("GITHUB_TOKEN")
        )
        self.timeout = float(
            timeout
        )
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ROVEBURY-Council/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if self.token:
            headers["Authorization"] = (
                f"Bearer {self.token}"
            )

        return headers

    def _api_url(
        self,
        suffix: str,
    ) -> str:
        repository = quote(
            self.repository_full_name,
            safe="/",
        )
        return (
            f"{GITHUB_API_BASE}/repos/"
            f"{repository}{suffix}"
        )

    async def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        async with httpx.AsyncClient(
            headers=self._headers(),
            timeout=self.timeout,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            response = await client.get(
                url,
                params=params,
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _observed_at() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _commit_message(
        payload: dict[str, Any],
    ) -> str:
        commit = payload.get(
            "commit",
            {},
        )
        message = str(
            commit.get(
                "message",
                "",
            )
        ).strip()

        if len(message) > MAX_COMMIT_MESSAGE_CHARS:
            return message[
                :MAX_COMMIT_MESSAGE_CHARS
            ]

        return message

    def _commit_evidence(
        self,
        payload: dict[str, Any],
        *,
        label: str,
        ref: str | None = None,
    ) -> dict[str, str]:
        sha = str(
            payload.get(
                "sha",
                "",
            )
        ).strip()
        html_url = str(
            payload.get(
                "html_url",
                "",
            )
        ).strip()
        message = self._commit_message(
            payload
        )

        author = (
            payload.get(
                "commit",
                {},
            )
            .get(
                "author",
                {},
            )
            .get(
                "name",
                "",
            )
        )

        lines = [
            f"Repository: {self.repository_full_name}",
            f"{label}: {sha}",
        ]

        if ref:
            lines.append(
                f"Ref: {ref}"
            )

        if message:
            lines.append(
                f"Commit message: {message}"
            )

        if author:
            lines.append(
                f"Commit author: {author}"
            )

        return {
            "source_name": (
                "GitHub repository "
                f"{self.repository_full_name}"
            ),
            "locator": html_url,
            "observed_at": self._observed_at(),
            "content": "\n".join(
                lines
            ),
        }

    async def __call__(
        self,
        request: dict[str, Any],
    ) -> list[dict[str, str]]:
        capability = str(
            request.get(
                "capability",
                "",
            )
        )

        if capability != CAPABILITY_GITHUB:
            raise ValueError(
                "GitHubReadProvider only accepts the github capability"
            )

        query = str(
            request.get(
                "query",
                "",
            )
        )

        intent = parse_github_read_intent(
            query,
            self.default_branch,
        )

        if intent.kind == "latest_commit":
            payload = await self._get_json(
                self._api_url(
                    "/commits"
                ),
                params={
                    "sha": intent.ref,
                    "per_page": 1,
                },
            )

            if not isinstance(
                payload,
                list,
            ) or not payload:
                return []

            return [
                self._commit_evidence(
                    payload[0],
                    label="Latest commit",
                    ref=intent.ref,
                )
            ]

        if intent.kind == "commit":
            sha = str(
                intent.commit_sha
                or ""
            )
            safe_sha = quote(
                sha,
                safe="",
            )
            payload = await self._get_json(
                self._api_url(
                    f"/commits/{safe_sha}"
                )
            )

            if not isinstance(
                payload,
                dict,
            ):
                return []

            return [
                self._commit_evidence(
                    payload,
                    label="Commit",
                )
            ]

        if intent.kind == "branch":
            ref = _safe_ref(
                intent.ref,
                self.default_branch,
            )
            safe_ref = quote(
                ref,
                safe="",
            )
            payload = await self._get_json(
                self._api_url(
                    f"/branches/{safe_ref}"
                )
            )

            if not isinstance(
                payload,
                dict,
            ):
                return []

            commit = payload.get(
                "commit",
                {},
            )

            if not isinstance(
                commit,
                dict,
            ):
                return []

            return [
                self._commit_evidence(
                    commit,
                    label="Branch head commit",
                    ref=ref,
                )
            ]

        payload = await self._get_json(
            self._api_url("")
        )

        if not isinstance(
            payload,
            dict,
        ):
            return []

        default_branch = str(
            payload.get(
                "default_branch",
                "",
            )
        )
        html_url = str(
            payload.get(
                "html_url",
                "",
            )
        )
        visibility = str(
            payload.get(
                "visibility",
                "",
            )
        )
        pushed_at = str(
            payload.get(
                "pushed_at",
                "",
            )
        )

        content = "\n".join(
            [
                f"Repository: {self.repository_full_name}",
                f"Default branch: {default_branch}",
                f"Visibility: {visibility}",
                f"Last pushed at: {pushed_at}",
            ]
        )

        return [
            {
                "source_name": (
                    "GitHub repository "
                    f"{self.repository_full_name}"
                ),
                "locator": html_url,
                "observed_at": self._observed_at(),
                "content": content,
            }
        ]


def build_github_read_provider(
    repository_full_name: str = DEFAULT_REPOSITORY,
    default_branch: str = DEFAULT_BRANCH,
    *,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GitHubReadProvider:
    """Construct the provider for explicit registry registration."""
    return GitHubReadProvider(
        repository_full_name=repository_full_name,
        default_branch=default_branch,
        token=token,
        timeout=timeout,
        transport=transport,
    )
