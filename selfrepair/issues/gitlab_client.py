"""GitLab Issues adapter for Issue Watch.

Implements `IssueProviderClient` over GitLab's REST v4 API.

API mapping:
  provider_issue_id  ← id (numeric, project-scoped stable)
  number             ← iid (human-visible, used in URLs)
  state              ← `opened`→`open` | `closed`→`closed`
  author             ← author.username
  labels             ← labels (already a list of strings)
  html_url           ← web_url

Project paths: GitLab REST requires URL-encoding the namespaced path
(`platform%2Fpayments-svc`) for the `:id` segment. We do that here so
the rest of the pipeline can use plain `org/repo` strings.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from selfrepair.issues.schemas import ExternalIssueDTO

logger = logging.getLogger(__name__)


class GitLabIssuesClient:
    provider = "gitlab"

    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://gitlab.com",
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/api/v4"
        self._client = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            headers={"PRIVATE-TOKEN": token},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_open_issues(
        self, repo_full_name: str, *, since_iso: str | None = None
    ) -> list[ExternalIssueDTO]:
        project = quote(repo_full_name, safe="")
        params: dict[str, Any] = {"state": "opened", "per_page": 100}
        if since_iso:
            params["updated_after"] = since_iso
        url = f"{self._base_url}/projects/{project}/issues"
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return [self._to_dto(item, repo_full_name) for item in resp.json()]

    async def get_issue(
        self, repo_full_name: str, issue_id: str
    ) -> ExternalIssueDTO | None:
        # `issue_id` is the project-scoped iid (URL-friendly), which is
        # what the route handler will pass through.
        project = quote(repo_full_name, safe="")
        url = f"{self._base_url}/projects/{project}/issues/{issue_id}"
        resp = await self._client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._to_dto(resp.json(), repo_full_name)

    async def comment(
        self, repo_full_name: str, issue_id: str, body: str
    ) -> str:
        project = quote(repo_full_name, safe="")
        url = f"{self._base_url}/projects/{project}/issues/{issue_id}/notes"
        resp = await self._client.post(url, json={"body": body})
        resp.raise_for_status()
        # GitLab notes don't carry an html_url; reconstruct from the issue
        # web_url + #note_id, which is stable.
        note_id = resp.json().get("id")
        return f"{self._base_url}/projects/{project}/issues/{issue_id}#note_{note_id}"

    async def close(
        self,
        repo_full_name: str,
        issue_id: str,
        comment: str | None = None,
    ) -> None:
        if comment:
            await self.comment(repo_full_name, issue_id, comment)
        project = quote(repo_full_name, safe="")
        url = f"{self._base_url}/projects/{project}/issues/{issue_id}"
        resp = await self._client.put(url, json={"state_event": "close"})
        resp.raise_for_status()

    @staticmethod
    def _to_dto(item: dict[str, Any], repo_full_name: str) -> ExternalIssueDTO:
        body = item.get("description") or ""
        gl_state = item.get("state", "opened")
        return ExternalIssueDTO(
            provider="gitlab",
            provider_issue_id=str(item.get("id")),
            repo_full_name=repo_full_name,
            number=int(item["iid"]),
            title=item.get("title") or "(no title)",
            body_excerpt=body[:2000] if body else None,
            state="closed" if gl_state == "closed" else "open",
            author=(item.get("author") or {}).get("username"),
            labels=tuple(item.get("labels") or []),
            assignees=tuple(
                (a.get("username") or "")
                for a in (item.get("assignees") or [])
                if a.get("username")
            ),
            html_url=item.get("web_url"),
            created_at=_parse_iso(item.get("created_at")),
            updated_at=_parse_iso(item.get("updated_at")),
            closed_at=_parse_iso(item.get("closed_at")),
            raw=item,
        )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
