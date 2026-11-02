"""Build the diff client and publisher for one event.

Injected test doubles win. Otherwise the worker mints an installation token
and posts the check. Missing credentials produce an explicit unpublished
result, not a recorded payload that looks like a successful GitHub check.
"""
from __future__ import annotations

import logging
from typing import Any

from selfrepair.auth.github_app import GitHubAppAuth
from selfrepair.reviewer.credentials import (
    github_token_for,
    gitlab_api_url,
    gitlab_token,
)
from selfrepair.reviewer.diff_provider import GitHubCompareProvider, GitLabCompareProvider
from selfrepair.reviewer.publishers import (
    GitHubHttpPublisher,
    GitLabHttpPublisher,
    HttpxTransport,
    UnpublishedPublisher,
)
from selfrepair.reviewer.schemas import RepoBinding, ReviewEvent
from selfrepair.reviewer.service import StaticDiffProvider

logger = logging.getLogger(__name__)


async def build_review_io(
    event: ReviewEvent,
    repo: RepoBinding,
    *,
    app: GitHubAppAuth | None = None,
) -> tuple[Any, Any]:
    """Return `(diff_provider, publisher)` for this repository event."""
    if event.provider == "gitlab":
        return _gitlab(event)
    installation_id = event.installation_id or repo.installation_id
    token = await github_token_for(installation_id, app=app)
    if not token:
        logger.info(
            "review has no github credentials repo=%s installation=%s",
            event.repo_full_name,
            installation_id,
        )
        return (
            StaticDiffProvider(error="diff provider not configured"),
            UnpublishedPublisher("github credentials unavailable"),
        )
    transport = HttpxTransport()
    return (
        GitHubCompareProvider(token=token, transport=transport),
        GitHubHttpPublisher(transport, token=token),
    )


def _gitlab(event: ReviewEvent) -> tuple[Any, Any]:
    token = gitlab_token()
    if not token or event.project_id is None:
        return (
            StaticDiffProvider(error="gitlab token or project id unavailable"),
            UnpublishedPublisher("gitlab credentials unavailable"),
        )
    api = f"{gitlab_api_url()}/api/v4"
    transport = HttpxTransport()
    return (
        GitLabCompareProvider(token=token, transport=transport, api_url=api),
        GitLabHttpPublisher(transport, token=token, api_url=api),
    )
