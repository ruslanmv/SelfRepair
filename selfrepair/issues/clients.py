"""Provider-neutral interface for the Issue Watch sync.

The sync service depends only on `IssueProviderClient` — a Protocol that
GitHub / GitLab / HuggingFace adapters satisfy structurally. This keeps
the call site oblivious to provider quirks (page-size limits, auth
headers, comment URLs).

`build_client(repo)` is the factory the worker uses; it returns a
fully-configured client based on `repo.provider` and per-provider env
credentials. None when no credentials are configured for that provider —
the sync skips the repo with a structured log line rather than crashing.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

from selfrepair.issues.schemas import ExternalIssueDTO

logger = logging.getLogger(__name__)


@runtime_checkable
class IssueProviderClient(Protocol):
    """Capability surface required from every provider adapter.

    Adapters MUST be safe to call with `await client.list_open_issues(repo)`
    in a worker context (no thread blocking; httpx.AsyncClient under the
    hood). They MUST raise `httpx.HTTPError` subclasses on transport
    failures so the sync service's retry/backoff path can catch them
    uniformly.
    """

    provider: str

    async def list_open_issues(
        self, repo_full_name: str, *, since_iso: str | None = None
    ) -> list[ExternalIssueDTO]: ...

    async def get_issue(
        self, repo_full_name: str, issue_id: str
    ) -> ExternalIssueDTO | None: ...

    async def comment(
        self, repo_full_name: str, issue_id: str, body: str
    ) -> str:
        """Returns the URL of the created comment."""
        ...

    async def close(
        self,
        repo_full_name: str,
        issue_id: str,
        comment: str | None = None,
    ) -> None: ...

    async def aclose(self) -> None: ...


def build_client(provider: str) -> IssueProviderClient | None:
    """Return a configured client for `provider`, or None when creds are missing.

    Per-provider env contract:
      github      → GITHUB_TOKEN
      gitlab      → GITLAB_TOKEN, optional GITLAB_BASE_URL (defaults to
                    https://gitlab.com)
      huggingface → HF_TOKEN, optional HF_BASE_URL (defaults to
                    https://huggingface.co)
    """
    # Lazy imports keep the CLI startup fast for the unrelated commands and
    # avoid importing httpx for tests that don't exercise the network path.
    if provider == "github":
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            logger.info(
                "issues clients: GITHUB_TOKEN not set; skipping github sync"
            )
            return None
        from selfrepair.issues.github_client import GitHubIssuesClient

        return GitHubIssuesClient(token=token)

    if provider == "gitlab":
        token = os.getenv("GITLAB_TOKEN")
        if not token:
            logger.info(
                "issues clients: GITLAB_TOKEN not set; skipping gitlab sync"
            )
            return None
        from selfrepair.issues.gitlab_client import GitLabIssuesClient

        return GitLabIssuesClient(
            token=token,
            base_url=os.getenv("GITLAB_BASE_URL", "https://gitlab.com"),
        )

    if provider == "huggingface":
        token = os.getenv("HF_TOKEN")
        if not token:
            logger.info(
                "issues clients: HF_TOKEN not set; skipping huggingface sync"
            )
            return None
        from selfrepair.issues.huggingface_client import HuggingFaceIssuesClient

        return HuggingFaceIssuesClient(
            token=token,
            base_url=os.getenv("HF_BASE_URL", "https://huggingface.co"),
        )

    logger.warning("issues clients: unknown provider %s", provider)
    return None
