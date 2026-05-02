"""Provider client adapters: GH, GL, HF.

Tests use `httpx.MockTransport` so no network is touched. The contracts
under test are:
  * each client returns DTOs that satisfy the Pydantic schema
  * provider quirks (PR filter, opened/open mapping, URL encoding) are
    handled in the adapter, not the call site
  * 404 on get_issue is normalised to None
  * comment/close issue the right HTTP method to the right path
"""
from __future__ import annotations

import json

import httpx
import pytest

pytest.importorskip("selfrepair")

from selfrepair.issues.github_client import GitHubIssuesClient  # noqa: E402
from selfrepair.issues.gitlab_client import GitLabIssuesClient  # noqa: E402
from selfrepair.issues.huggingface_client import HuggingFaceIssuesClient  # noqa: E402


def _transport(handler):
    """Build a MockTransport. Tests inject this so adapters' own auth
    headers are still applied to outgoing requests."""
    return httpx.MockTransport(handler)


# ---------------- GitHub ----------------


class TestGitHubClient:
    @pytest.mark.asyncio
    async def test_list_open_issues_filters_pull_requests(self) -> None:
        body = [
            {
                "id": 1,
                "node_id": "MDU6SXNzdWUx",
                "number": 12,
                "title": "CI fails",
                "body": "Repro on fresh clone",
                "state": "open",
                "user": {"login": "alice"},
                "labels": [{"name": "bug"}, {"name": "ci"}],
                "assignees": [],
                "html_url": "https://github.com/octo/x/issues/12",
                "created_at": "2026-05-02T08:00:00Z",
                "updated_at": "2026-05-02T08:30:00Z",
                "closed_at": None,
            },
            {
                # PR-shaped issue — must be filtered out
                "id": 2,
                "node_id": "PR_y",
                "number": 13,
                "title": "PR title",
                "pull_request": {"url": "..."},
                "state": "open",
                "user": {"login": "bob"},
                "labels": [],
                "assignees": [],
                "html_url": "https://github.com/octo/x/pull/13",
            },
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/repos/octo/x/issues"
            assert request.url.params["state"] == "open"
            return httpx.Response(200, json=body)

        client = GitHubIssuesClient(token="t", transport=_transport(handler))
        try:
            out = await client.list_open_issues("octo/x")
        finally:
            await client.aclose()

        assert len(out) == 1
        issue = out[0]
        assert issue.provider == "github"
        assert issue.number == 12
        assert issue.author == "alice"
        assert issue.labels == ("bug", "ci")
        assert issue.html_url == "https://github.com/octo/x/issues/12"

    @pytest.mark.asyncio
    async def test_get_issue_404_returns_none(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        client = GitHubIssuesClient(token="t", transport=_transport(handler))
        try:
            out = await client.get_issue("octo/x", "999")
        finally:
            await client.aclose()
        assert out is None

    @pytest.mark.asyncio
    async def test_comment_posts_to_comments_endpoint(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content.decode())
            return httpx.Response(
                201,
                json={"html_url": "https://github.com/octo/x/issues/12#c-1"},
            )

        client = GitHubIssuesClient(token="t", transport=_transport(handler))
        try:
            url = await client.comment("octo/x", "12", "hello")
        finally:
            await client.aclose()
        assert seen["method"] == "POST"
        assert seen["path"] == "/repos/octo/x/issues/12/comments"
        assert seen["body"] == {"body": "hello"}
        assert url.endswith("#c-1")


# ---------------- GitLab ----------------


class TestGitLabClient:
    @pytest.mark.asyncio
    async def test_list_open_issues_url_encodes_namespaced_path(self) -> None:
        body = [
            {
                "id": 901,
                "iid": 901,
                "title": "Release missing SBOM",
                "description": "...",
                "state": "opened",
                "author": {"username": "devops"},
                "labels": ["release", "compliance"],
                "assignees": [],
                "web_url": "https://gitlab.com/platform/audit-ledger/-/issues/901",
                "created_at": "2026-05-02T07:00:00Z",
                "updated_at": "2026-05-02T07:30:00Z",
                "closed_at": None,
            }
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            # Project segment must be %2F-encoded
            assert "%2F" in str(request.url)
            assert request.url.params["state"] == "opened"
            assert request.headers["PRIVATE-TOKEN"] == "t"
            return httpx.Response(200, json=body)

        client = GitLabIssuesClient(token="t", transport=_transport(handler))
        try:
            out = await client.list_open_issues("platform/audit-ledger")
        finally:
            await client.aclose()
        assert len(out) == 1
        issue = out[0]
        # `opened` → `open`
        assert issue.state == "open"
        assert issue.labels == ("release", "compliance")
        assert issue.html_url.endswith("issues/901")

    @pytest.mark.asyncio
    async def test_close_uses_state_event_close(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={})

        client = GitLabIssuesClient(token="t", transport=_transport(handler))
        try:
            await client.close("platform/x", "1")
        finally:
            await client.aclose()
        assert seen["method"] == "PUT"
        assert seen["body"] == {"state_event": "close"}


# ---------------- HuggingFace ----------------


class TestHuggingFaceClient:
    @pytest.mark.asyncio
    async def test_list_filters_pull_requests(self) -> None:
        body = {
            "discussions": [
                {
                    "num": 77,
                    "title": "Space won't start",
                    "content": "ImportError…",
                    "status": "open",
                    "author": {"name": "community-user"},
                    "createdAt": "2026-05-02T06:00:00Z",
                    "updatedAt": "2026-05-02T06:30:00Z",
                },
                {
                    "num": 78,
                    "title": "Bump deps",
                    "isPullRequest": True,
                    "status": "open",
                },
            ]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            assert "discussions" in request.url.path
            return httpx.Response(200, json=body)

        client = HuggingFaceIssuesClient(token="t", transport=_transport(handler))
        try:
            out = await client.list_open_issues("huggingface/granite-medical")
        finally:
            await client.aclose()
        assert len(out) == 1
        issue = out[0]
        assert issue.provider == "huggingface"
        assert issue.number == 77
        assert issue.html_url.endswith("discussions/77")

    @pytest.mark.asyncio
    async def test_space_repo_type_uses_spaces_path(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            return httpx.Response(200, json={"discussions": []})

        client = HuggingFaceIssuesClient(
            token="t", repo_type="space", transport=_transport(handler)
        )
        try:
            await client.list_open_issues("ns/space")
        finally:
            await client.aclose()
        assert "/api/spaces/ns/space/discussions" in seen["path"]


# ---------------- Factory ----------------


class TestBuildClient:
    def test_returns_none_when_token_missing(self, monkeypatch) -> None:
        from selfrepair.issues.clients import build_client

        for env in ("GITHUB_TOKEN", "GITLAB_TOKEN", "HF_TOKEN"):
            monkeypatch.delenv(env, raising=False)
        assert build_client("github") is None
        assert build_client("gitlab") is None
        assert build_client("huggingface") is None

    def test_unknown_provider_returns_none(self, monkeypatch) -> None:
        from selfrepair.issues.clients import build_client

        assert build_client("not_a_provider") is None

    def test_returns_client_when_token_set(self, monkeypatch) -> None:
        from selfrepair.issues.clients import build_client

        monkeypatch.setenv("GITHUB_TOKEN", "t")
        client = build_client("github")
        assert client is not None
        assert client.provider == "github"
