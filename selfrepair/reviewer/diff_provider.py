"""Fetch a GitHub compare diff without cloning onto the worker.

The existing clone stage is a depth-1 checkout of the default branch and
cannot see a push `before` SHA. This provider uses the compare API. A missing
token is an explicit incomplete review, not an empty success.
"""
from __future__ import annotations

import os
from typing import Any

from selfrepair.reviewer.diff import limit_diff, parse_github_files
from selfrepair.reviewer.schemas import (
    ZERO_SHA,
    DiffSet,
    RepoBinding,
    ReviewEvent,
    TransientReviewError,
)


class GitHubCompareProvider:
    """Read-only compare client.

    `transport.get` returns an object with `status_code`, `json()`, and `headers`.
    """

    def __init__(
        self,
        token: str,
        transport: Any | None = None,
        api_url: str = "https://api.github.com",
    ) -> None:
        self._token = token
        self._transport = transport
        self._api = api_url.rstrip("/")

    async def collect(self, event: ReviewEvent, repo: RepoBinding) -> DiffSet:
        """Return the compare diff for `base...head`."""
        del repo
        if not self._token:
            return DiffSet(source="github", error="installation token unavailable")
        base = event.default_branch if event.base_sha == ZERO_SHA else event.base_sha
        url = f"{self._api}/repos/{event.repo_full_name}/compare/{base}...{event.head_sha}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        response = await self._get(url, headers)
        status = getattr(response, "status_code", 0)
        if status == 429:
            raise TransientReviewError("github compare rate limited")
        if status == 404:
            return DiffSet(source="github", error="compare unavailable for this SHA range")
        if status >= 400:
            return DiffSet(source="github", error=f"compare failed with HTTP {status}")
        body = response.json()
        files = parse_github_files(body.get("files") or [])
        limited = limit_diff(files)
        limited.source = "github-compare"
        return limited

    async def _get(self, url: str, headers: dict[str, str]) -> Any:
        if self._transport is not None:
            return await self._transport.get(url, headers=headers)
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.get(url, headers=headers)


def provider_from_env() -> Any:
    """Use a GitHub token from the environment, or an explicit unavailable diff."""
    from selfrepair.reviewer.service import StaticDiffProvider

    token = os.getenv("SELFREPAIR_GITHUB_TOKEN", "").strip()
    if not token:
        return StaticDiffProvider(error="diff provider not configured")
    return GitHubCompareProvider(token=token)
