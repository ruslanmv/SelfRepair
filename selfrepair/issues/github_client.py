"""GitHub Issues adapter for Issue Watch.

Implements `IssueProviderClient` over the GitHub REST v3 API.

API mapping (the only place provider quirks should live):
  provider_issue_id  ← node_id  (stable across renumbers)
  number             ← number   (human-visible, used in URLs)
  state              ← state    (open/closed)
  author             ← user.login
  labels             ← labels[].name
  html_url           ← html_url

PR-shaped issues are filtered out — the GitHub Issues API mixes them in
and we don't want a PR to surface as a human-reported issue here.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from selfrepair.issues.schemas import ExternalIssueDTO

logger = logging.getLogger(__name__)


class GitHubIssuesClient:
    provider = "github"

    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://api.github.com",
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # Tests inject a `MockTransport`; production omits transport so httpx
        # uses the real network. Auth headers are owned by this class either way.
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_open_issues(
        self, repo_full_name: str, *, since_iso: str | None = None
    ) -> list[ExternalIssueDTO]:
        """Single page (per_page=100). Pagination is the sync service's job
        when GH returns a Link header — kept out of the adapter so the
        Protocol stays slim. Phase-1 ships single-page only; large repos
        get the most-recently-updated 100 open issues, which is enough to
        prove the path."""
        params: dict[str, Any] = {"state": "open", "per_page": 100}
        if since_iso:
            params["since"] = since_iso
        url = f"{self._base_url}/repos/{repo_full_name}/issues"
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return [
            self._to_dto(item, repo_full_name)
            for item in resp.json()
            if "pull_request" not in item  # filter PR-shaped issues
        ]

    async def get_issue(
        self, repo_full_name: str, issue_id: str
    ) -> ExternalIssueDTO | None:
        # `issue_id` is the human-visible number in GitHub's URL contract.
        url = f"{self._base_url}/repos/{repo_full_name}/issues/{issue_id}"
        resp = await self._client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._to_dto(resp.json(), repo_full_name)

    async def comment(
        self, repo_full_name: str, issue_id: str, body: str
    ) -> str:
        url = f"{self._base_url}/repos/{repo_full_name}/issues/{issue_id}/comments"
        resp = await self._client.post(url, json={"body": body})
        resp.raise_for_status()
        return resp.json().get("html_url", "")

    async def close(
        self,
        repo_full_name: str,
        issue_id: str,
        comment: str | None = None,
    ) -> None:
        if comment:
            await self.comment(repo_full_name, issue_id, comment)
        url = f"{self._base_url}/repos/{repo_full_name}/issues/{issue_id}"
        resp = await self._client.patch(url, json={"state": "closed"})
        resp.raise_for_status()

    @staticmethod
    def _to_dto(item: dict[str, Any], repo_full_name: str) -> ExternalIssueDTO:
        body = item.get("body") or ""
        return ExternalIssueDTO(
            provider="github",
            provider_issue_id=str(item.get("node_id") or item.get("id")),
            repo_full_name=repo_full_name,
            number=int(item["number"]),
            title=item.get("title") or "(no title)",
            body_excerpt=body[:2000] if body else None,
            state="closed" if item.get("state") == "closed" else "open",
            author=(item.get("user") or {}).get("login"),
            labels=tuple(
                (label.get("name") or "")
                for label in (item.get("labels") or [])
                if label.get("name")
            ),
            assignees=tuple(
                (a.get("login") or "")
                for a in (item.get("assignees") or [])
                if a.get("login")
            ),
            html_url=item.get("html_url"),
            created_at=_parse_iso(item.get("created_at")),
            updated_at=_parse_iso(item.get("updated_at")),
            closed_at=_parse_iso(item.get("closed_at")),
            raw=item,
        )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # GitHub returns trailing Z; datetime.fromisoformat handles it on 3.11+
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
