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
        if event.kind == "pull_request" and event.pr_number is not None:
            url = (
                f"{self._api}/repos/{event.repo_full_name}/pulls/"
                f"{event.pr_number}/files?per_page=100"
            )
            source = "github-pull-files"
        else:
            source = "github-compare"
        response = await self._get(url, headers)
        failed = _http_failure(response, source="github")
        if failed is not None:
            return failed
        body = response.json()
        if isinstance(body, list):
            payload = body
            page_full = len(body) >= 100
        else:
            payload = body.get("files") or []
            page_full = False
        files = parse_github_files(payload)
        limited = limit_diff(files)
        limited.source = source
        if page_full:
            limited.truncated = True
        return limited

    async def _get(self, url: str, headers: dict[str, str]) -> Any:
        if self._transport is not None:
            return await self._transport.get(url, headers=headers)
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.get(url, headers=headers)


class GitLabCompareProvider:
    """Read a merge-request diff from the GitLab compare API. No clone."""

    def __init__(
        self,
        token: str,
        transport: Any | None = None,
        api_url: str = "https://gitlab.com/api/v4",
    ) -> None:
        self._token = token
        self._transport = transport
        self._api = api_url.rstrip("/")

    async def collect(self, event: ReviewEvent, repo: RepoBinding) -> DiffSet:
        """Return the compare diff for the merge request head."""
        del repo
        if not self._token or event.project_id is None:
            return DiffSet(source="gitlab", error="gitlab token or project id unavailable")
        base = event.default_branch if event.base_sha == ZERO_SHA else event.base_sha
        url = (
            f"{self._api}/projects/{event.project_id}/repository/compare"
            f"?from={base}&to={event.head_sha}"
        )
        headers = {"PRIVATE-TOKEN": self._token}
        response = await self._get(url, headers)
        failed = _http_failure(response, source="gitlab")
        if failed is not None:
            return failed
        body = response.json()
        files = _gitlab_files(body.get("diffs") or [])
        limited = limit_diff(files)
        limited.source = "gitlab-compare"
        if body.get("compare_timeout"):
            limited.truncated = True
        return limited

    async def _get(self, url: str, headers: dict[str, str]) -> Any:
        if self._transport is not None:
            return await self._transport.get(url, headers=headers)
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.get(url, headers=headers)


def _http_failure(response: Any, *, source: str) -> DiffSet | None:
    """Map an HTTP error to a diff error, or raise when GitHub/GitLab asked us to retry."""
    status = getattr(response, "status_code", 0)
    if status == 429 or (status == 403 and _rate_limited(response)):
        raise TransientReviewError(f"{source} compare rate limited")
    if status == 404:
        return DiffSet(source=source, error="compare unavailable for this SHA range")
    if status >= 400:
        return DiffSet(source=source, error=f"compare failed with HTTP {status}")
    return None


def _rate_limited(response: Any) -> bool:
    headers = getattr(response, "headers", {}) or {}
    return headers.get("x-ratelimit-remaining") == "0" or headers.get("ratelimit-remaining") == "0"


def _gitlab_files(diffs: list[dict[str, Any]]) -> list[Any]:
    from selfrepair.reviewer.diff import parse_unified_diff
    from selfrepair.reviewer.schemas import DiffFile

    files: list[DiffFile] = []
    for item in diffs:
        new_path = item.get("new_path") or item.get("old_path") or "unknown"
        old_path = item.get("old_path") or new_path
        patch = item.get("diff") or ""
        if item.get("binary") or not patch:
            files.append(
                DiffFile(
                    path=new_path,
                    previous_path=old_path if old_path != new_path else None,
                    status="binary" if item.get("binary") else _gitlab_status(item),
                    patch="",
                )
            )
            continue
        wrapped = (
            f"diff --git a/{old_path} b/{new_path}\n"
            f"--- a/{old_path}\n+++ b/{new_path}\n{patch}"
        )
        parsed = parse_unified_diff(wrapped)
        if not parsed:
            continue
        file = parsed[0]
        file.path = new_path
        file.previous_path = old_path if old_path != new_path else None
        file.status = _gitlab_status(item)
        files.append(file)
    return files


def _gitlab_status(item: dict[str, Any]) -> Any:
    if item.get("deleted_file"):
        return "removed"
    if item.get("new_file"):
        return "added"
    if item.get("renamed_file"):
        return "renamed"
    return "modified"


def provider_from_env() -> Any:
    """Use a GitHub token from the environment, or an explicit unavailable diff."""
    from selfrepair.reviewer.service import StaticDiffProvider

    token = os.getenv("SELFREPAIR_GITHUB_TOKEN", "").strip()
    if not token:
        return StaticDiffProvider(error="diff provider not configured")
    return GitHubCompareProvider(token=token)
