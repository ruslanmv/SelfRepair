"""Webhook dispatch for Issue Watch.

Contracts:
  * Kill switch is honoured first.
  * Unknown event types return `ignored`.
  * Unknown repos (no matching `repo` row) return `ignored` and persist
    nothing.
  * `issue_comment` (GitHub) and `Note Hook` (GitLab) acknowledge but
    do not mutate (Phase-2 stores comments).
  * The persisted DTO has the right provider + repo_full_name.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("selfrepair")
pytest.importorskip("pydantic")

from selfrepair.issues import dispatcher  # noqa: E402
from selfrepair.issues.config import IssueWatchRuntime  # noqa: E402


def _runtime(*, kill: bool = False) -> IssueWatchRuntime:
    return IssueWatchRuntime(
        kill_switch=kill,
        sync_window_minutes=15,
        page_size=50,
        request_timeout_seconds=15.0,
        huggingface_enabled=True,
    )


def _gh_payload() -> dict:
    return {
        "action": "opened",
        "issue": {
            "id": 1,
            "node_id": "MDU6SXNzdWUx",
            "number": 12,
            "title": "CI fails",
            "body": "...",
            "state": "open",
            "user": {"login": "alice"},
            "labels": [{"name": "bug"}],
            "assignees": [],
            "html_url": "https://github.com/octo/x/issues/12",
            "created_at": "2026-05-02T08:00:00Z",
            "updated_at": "2026-05-02T08:30:00Z",
        },
        "repository": {"id": 1, "full_name": "octo/x"},
    }


def _gl_payload() -> dict:
    return {
        "object_kind": "issue",
        "user": {"username": "devops"},
        "project": {"path_with_namespace": "platform/audit-ledger"},
        "object_attributes": {
            "id": 901,
            "iid": 901,
            "title": "Release missing SBOM",
            "description": "...",
            "state": "opened",
            "url": "https://gitlab.com/platform/audit-ledger/-/issues/901",
            "created_at": "2026-05-02T07:00:00Z",
            "updated_at": "2026-05-02T07:30:00Z",
        },
        "labels": [{"title": "release"}],
        "assignees": [],
    }


class TestKillSwitch:
    @pytest.mark.asyncio
    async def test_github_kill_switch_drops_event(self) -> None:
        with patch.object(dispatcher, "get_runtime", return_value=_runtime(kill=True)):
            out = await dispatcher.dispatch_github_issue_event(
                ctx={}, event_type="issues",
                delivery_id="d", payload=_gh_payload(),
            )
        assert out == "ignored"

    @pytest.mark.asyncio
    async def test_gitlab_kill_switch_drops_event(self) -> None:
        with patch.object(dispatcher, "get_runtime", return_value=_runtime(kill=True)):
            out = await dispatcher.dispatch_gitlab_issue_event(
                ctx={}, event_type="Issue Hook", payload=_gl_payload(),
            )
        assert out == "ignored"


class TestEventFilters:
    @pytest.mark.asyncio
    async def test_github_issue_comment_acknowledges_only(self) -> None:
        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_github_issue_event(
                ctx={}, event_type="issue_comment",
                delivery_id="d", payload=_gh_payload(),
            )
        assert out == "tracked"

    @pytest.mark.asyncio
    async def test_unknown_github_event_is_ignored(self) -> None:
        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_github_issue_event(
                ctx={}, event_type="not_a_thing",
                delivery_id="d", payload=_gh_payload(),
            )
        assert out == "ignored"

    @pytest.mark.asyncio
    async def test_gitlab_note_hook_acknowledges_only(self) -> None:
        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_gitlab_issue_event(
                ctx={}, event_type="Note Hook", payload=_gl_payload(),
            )
        assert out == "tracked"

    @pytest.mark.asyncio
    async def test_github_pr_shaped_issue_is_ignored(self) -> None:
        # GH re-emits PR events on the issues channel; must not persist.
        payload = _gh_payload()
        payload["issue"]["pull_request"] = {"url": "..."}
        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_github_issue_event(
                ctx={}, event_type="issues",
                delivery_id="d", payload=payload,
            )
        assert out == "ignored"


class TestPersistence:
    @pytest.mark.asyncio
    async def test_unknown_repo_is_ignored(self) -> None:
        # Sessionmaker yields a session whose execute() resolves to None
        # for the repo lookup → dispatcher returns "ignored".
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        sessionmaker = MagicMock(return_value=session)

        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_github_issue_event(
                ctx={"sessionmaker": sessionmaker},
                event_type="issues",
                delivery_id="d",
                payload=_gh_payload(),
            )
        assert out == "ignored"
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_known_repo_upserts_dto(self) -> None:
        # Plumb through a sessionmaker whose repo lookup returns a real-ish
        # Repo, and patch _upsert_one so we can assert what it received.
        repo = SimpleNamespace(
            id="r", org_id="o", provider="github", full_name="octo/x"
        )
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=repo)
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        sessionmaker = MagicMock(return_value=session)

        with patch.object(dispatcher, "get_runtime", return_value=_runtime()), \
             patch.object(dispatcher, "_upsert_one", new_callable=AsyncMock) as upsert:
            out = await dispatcher.dispatch_github_issue_event(
                ctx={"sessionmaker": sessionmaker},
                event_type="issues",
                delivery_id="d",
                payload=_gh_payload(),
            )
        assert out == "tracked"
        upsert.assert_awaited_once()
        kwargs = upsert.call_args.kwargs
        assert kwargs["dto"].provider == "github"
        assert kwargs["dto"].repo_full_name == "octo/x"
        session.commit.assert_awaited_once()
