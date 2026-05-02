"""Issue Watch service orchestration.

Contracts under test (the load-bearing ones):
  * Missing client (no creds) → empty SyncReport, never crashes.
  * One DTO upserts; classification + repairability decided correctly.
  * One client failure produces errors=1, doesn't propagate.
  * Reconciliation closes only rows the provider didn't return — and
    only when the fetched page is non-empty.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("selfrepair")
pytest.importorskip("pydantic")

from selfrepair.issues.schemas import ExternalIssueDTO  # noqa: E402
from selfrepair.issues.service import sync_repo_issues  # noqa: E402


def _repo(provider="github", full_name="octo/x"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        provider=provider,
        full_name=full_name,
    )


def _dto(provider_issue_id="42", title="CI fails on missing pyproject"):
    return ExternalIssueDTO(
        provider="github",
        provider_issue_id=provider_issue_id,
        repo_full_name="octo/x",
        number=int(provider_issue_id) if provider_issue_id.isdigit() else 1,
        title=title,
        labels=("bug", "ci"),
    )


class _FakeClient:
    provider = "github"

    def __init__(self, dtos=None, raise_on_list=None):
        self._dtos = dtos or []
        self._raise = raise_on_list
        self.aclosed = False

    async def list_open_issues(self, *_args, **_kwargs):
        if self._raise is not None:
            raise self._raise
        return self._dtos

    async def get_issue(self, *args, **kwargs):
        return None

    async def comment(self, *args, **kwargs):
        return ""

    async def close(self, *args, **kwargs):
        return None

    async def aclose(self):
        self.aclosed = True


def _issues_repo():
    repo = MagicMock()
    repo.upsert_issue = AsyncMock()
    repo.list_issues = AsyncMock(return_value=[])
    repo.mark_closed = AsyncMock()
    return repo


class TestSyncRepoIssues:
    @pytest.mark.asyncio
    async def test_no_client_returns_empty_report(self) -> None:
        repo = _repo()
        report = await sync_repo_issues(
            repo=repo,
            issues_repo=_issues_repo(),
            client_factory=lambda _p: None,
        )
        assert report.upserted == 0
        assert report.errors == 0

    @pytest.mark.asyncio
    async def test_one_dto_upserts_with_classification(self) -> None:
        repo = _repo()
        client = _FakeClient(dtos=[_dto()])
        issues_repo = _issues_repo()
        report = await sync_repo_issues(
            repo=repo,
            issues_repo=issues_repo,
            client_factory=lambda _p: client,
        )
        assert report.upserted == 1
        assert report.errors == 0
        # client released
        assert client.aclosed is True

        kwargs = issues_repo.upsert_issue.call_args.kwargs
        assert kwargs["repair_class"] == "ci_failure"
        # CI failure class defaults to REVIEW (not ESCALATE) → repairable
        assert kwargs["repairable"] is True
        assert kwargs["fingerprint"]
        assert kwargs["priority"] == "medium"

    @pytest.mark.asyncio
    async def test_security_dto_marked_not_repairable(self) -> None:
        repo = _repo()
        sec = ExternalIssueDTO(
            provider="github",
            provider_issue_id="13",
            repo_full_name="octo/x",
            number=13,
            title="Possible secret leak in .env.example",
            labels=("security",),
        )
        client = _FakeClient(dtos=[sec])
        issues_repo = _issues_repo()
        await sync_repo_issues(
            repo=repo,
            issues_repo=issues_repo,
            client_factory=lambda _p: client,
        )
        kwargs = issues_repo.upsert_issue.call_args.kwargs
        assert kwargs["repair_class"] == "security"
        assert kwargs["repairable"] is False

    @pytest.mark.asyncio
    async def test_list_failure_isolates_to_one_error(self) -> None:
        repo = _repo()
        client = _FakeClient(raise_on_list=RuntimeError("rate limited"))
        report = await sync_repo_issues(
            repo=repo,
            issues_repo=_issues_repo(),
            client_factory=lambda _p: client,
        )
        assert report.errors == 1
        assert report.upserted == 0

    @pytest.mark.asyncio
    async def test_reconciliation_closes_missing_rows(self) -> None:
        repo = _repo()
        client = _FakeClient(dtos=[_dto(provider_issue_id="42")])
        issues_repo = _issues_repo()
        # Existing row not in the fresh response → must be closed.
        existing = SimpleNamespace(
            id=uuid.uuid4(),
            provider="github",
            provider_issue_id="999",
        )
        # And one row that IS in the fresh response → must NOT be closed.
        kept = SimpleNamespace(
            id=uuid.uuid4(),
            provider="github",
            provider_issue_id="42",
        )
        issues_repo.list_issues.return_value = [existing, kept]

        report = await sync_repo_issues(
            repo=repo,
            issues_repo=issues_repo,
            client_factory=lambda _p: client,
        )
        assert report.closed_reconciled == 1
        issues_repo.mark_closed.assert_awaited_once_with(existing.id)

    @pytest.mark.asyncio
    async def test_empty_response_skips_reconciliation(self) -> None:
        # Provider returned 0 issues — must be treated as "transient" and
        # NOT mark every existing row closed.
        repo = _repo()
        client = _FakeClient(dtos=[])
        issues_repo = _issues_repo()
        issues_repo.list_issues.return_value = [
            SimpleNamespace(
                id=uuid.uuid4(),
                provider="github",
                provider_issue_id="999",
            )
        ]
        report = await sync_repo_issues(
            repo=repo,
            issues_repo=issues_repo,
            client_factory=lambda _p: client,
        )
        assert report.closed_reconciled == 0
        issues_repo.mark_closed.assert_not_awaited()
