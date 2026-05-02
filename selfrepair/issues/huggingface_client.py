"""Hugging Face Community Discussions adapter for Issue Watch.

HF doesn't have GitHub-style Issues; the equivalent surface is the
**Community Discussions** tab on each repo (model, dataset, or space).
We treat each discussion as one external issue.

Repos in HF are namespaced as `<owner>/<name>` and live under one of three
endpoints depending on type. The phase-1 implementation supports models
(default) and spaces; datasets follow the same shape and can be added
behind an env flag if needed.

API mapping:
  provider_issue_id  ← discussion.num (stable per repo)
  number             ← discussion.num (HF uses one id, not two)
  state              ← `open`/`closed`
  author             ← author.name
  labels             ← (none — HF discussions don't have labels yet)
  html_url           ← f"{base}/<owner>/<name>/discussions/<num>"

Discussion vs. PR: HF marks PRs in the same discussion list with
`isPullRequest=True`. We filter those out so users see human-reported
issues only, mirroring the GitHub PR-filter on the GitHub adapter.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from selfrepair.issues.schemas import ExternalIssueDTO

logger = logging.getLogger(__name__)


class HuggingFaceIssuesClient:
    """HF discussions API.

    repo_full_name is `owner/name`. For `space:` or `dataset:` prefixes the
    sync service is expected to strip them before calling — the adapter
    handles plain owner/name and assumes `model` repo type by default.
    """

    provider = "huggingface"

    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://huggingface.co",
        repo_type: str = "model",
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._repo_type = repo_type
        self._client = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _api_path(self, repo_full_name: str) -> str:
        # Models live under /api/{owner}/{name}/discussions
        # Spaces live under /api/spaces/{owner}/{name}/discussions
        # Datasets under /api/datasets/{owner}/{name}/discussions
        if self._repo_type == "space":
            return f"{self._base_url}/api/spaces/{repo_full_name}/discussions"
        if self._repo_type == "dataset":
            return f"{self._base_url}/api/datasets/{repo_full_name}/discussions"
        return f"{self._base_url}/api/{repo_full_name}/discussions"

    async def list_open_issues(
        self, repo_full_name: str, *, since_iso: str | None = None
    ) -> list[ExternalIssueDTO]:
        params: dict[str, Any] = {"status": "open", "type": "discussion"}
        url = self._api_path(repo_full_name)
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json() or {}
        items = payload.get("discussions", payload) or []
        return [
            self._to_dto(item, repo_full_name)
            for item in items
            if not item.get("isPullRequest")
        ]

    async def get_issue(
        self, repo_full_name: str, issue_id: str
    ) -> ExternalIssueDTO | None:
        url = f"{self._api_path(repo_full_name)}/{issue_id}"
        resp = await self._client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._to_dto(resp.json(), repo_full_name)

    async def comment(
        self, repo_full_name: str, issue_id: str, body: str
    ) -> str:
        url = f"{self._api_path(repo_full_name)}/{issue_id}/comment"
        resp = await self._client.post(url, json={"comment": body})
        resp.raise_for_status()
        return f"{self._base_url}/{repo_full_name}/discussions/{issue_id}"

    async def close(
        self,
        repo_full_name: str,
        issue_id: str,
        comment: str | None = None,
    ) -> None:
        if comment:
            await self.comment(repo_full_name, issue_id, comment)
        url = f"{self._api_path(repo_full_name)}/{issue_id}/status"
        resp = await self._client.post(url, json={"status": "closed"})
        resp.raise_for_status()

    @staticmethod
    def _to_dto(item: dict[str, Any], repo_full_name: str) -> ExternalIssueDTO:
        body = item.get("content") or item.get("body") or ""
        num = item.get("num") or item.get("number") or 0
        return ExternalIssueDTO(
            provider="huggingface",
            provider_issue_id=str(num),
            repo_full_name=repo_full_name,
            number=int(num) if int(num) > 0 else 1,
            title=item.get("title") or "(no title)",
            body_excerpt=body[:2000] if body else None,
            state="closed" if item.get("status") == "closed" else "open",
            author=(item.get("author") or {}).get("name"),
            labels=(),
            assignees=(),
            html_url=f"https://huggingface.co/{repo_full_name}/discussions/{num}",
            created_at=_parse_iso(item.get("createdAt")),
            updated_at=_parse_iso(item.get("updatedAt")),
            closed_at=_parse_iso(item.get("closedAt")),
            raw=item,
        )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
