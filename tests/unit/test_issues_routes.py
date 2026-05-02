"""FastAPI Issue Watch endpoint tests.

The route layer's contract is shape, not SQL. Given a repository that
returns a row, it must serialise it correctly and translate 404 / 409 cases
into HTTP responses. Repository methods are mocked via the dependency
override so we don't need a real database.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from selfrepair.api.routes import issues as issues_route  # noqa: E402
from selfrepair.persistence.models import ExternalIssueActionType  # noqa: E402


@pytest.fixture
def fake_repo(monkeypatch):
    """Replace the IssuesRepository and JobsRepository so route handlers
    receive programmable doubles, and override the session dependency so
    no real DB is touched.
    """
    issues_repo = MagicMock()
    issues_repo.list_issues = AsyncMock(return_value=[])
    issues_repo.get_issue = AsyncMock()
    issues_repo.list_actions_for_issue = AsyncMock(return_value=[])
    issues_repo.record_action = AsyncMock()

    jobs_repo = MagicMock()
    jobs_repo.create = AsyncMock()

    monkeypatch.setattr(issues_route, "IssuesRepository", lambda _s: issues_repo)
    monkeypatch.setattr(issues_route, "JobsRepository", lambda _s: jobs_repo)

    async def _fake_session():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    from selfrepair.api.main import build_app

    app = build_app()
    app.dependency_overrides[issues_route._session] = _fake_session
    app.state.queue = MagicMock()
    app.state.queue.enqueue_job = AsyncMock()
    return issues_repo, jobs_repo, app


def _issue_row(**overrides):
    base = dict(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        provider="github",
        provider_issue_id="42",
        number=42,
        title="CI fails when pyproject deps are missing",
        body_excerpt="uv sync exits 1 when [tool.uv] is absent",
        state="open",
        author="human-user",
        labels=["bug", "ci"],
        assignees=[],
        priority="high",
        repair_class="ci_failure",
        repairable=True,
        html_url="https://github.com/octo/x/issues/42",
        created_at_external=datetime.now(UTC),
        updated_at_external=datetime.now(UTC),
        closed_at_external=None,
        last_synced_at=datetime.now(UTC),
        fingerprint="f" * 32,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _action_row(**overrides):
    base = dict(
        id=uuid.uuid4(),
        action_type=ExternalIssueActionType.RUN_REPAIR,
        action_status="queued",
        actor="ruslan@selfrepair.dev",
        job_id=uuid.uuid4(),
        finding_id=None,
        repair_id=None,
        comment_url=None,
        created_at=datetime.now(UTC),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _job_row():
    return SimpleNamespace(id=uuid.uuid4())


class TestListIssues:
    def test_returns_serialised_items(self, fake_repo) -> None:
        issues_repo, _jobs, app = fake_repo
        issues_repo.list_issues.return_value = [_issue_row()]
        client = TestClient(app)
        resp = client.get(f"/v1/issues?org_id={uuid.uuid4()}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        item = body["items"][0]
        assert item["repair_class"] == "ci_failure"
        assert item["repairable"] is True
        assert item["labels"] == ["bug", "ci"]

    def test_org_id_is_required(self, fake_repo) -> None:
        _issues, _jobs, app = fake_repo
        client = TestClient(app)
        resp = client.get("/v1/issues")
        assert resp.status_code == 422

    def test_filters_pass_through(self, fake_repo) -> None:
        issues_repo, _jobs, app = fake_repo
        issues_repo.list_issues.return_value = []
        client = TestClient(app)
        org_id = uuid.uuid4()
        resp = client.get(
            f"/v1/issues?org_id={org_id}"
            "&provider=gitlab&state=open&priority=high&repairable=true"
        )
        assert resp.status_code == 200
        kwargs = issues_repo.list_issues.call_args.kwargs
        assert kwargs["provider"] == "gitlab"
        assert kwargs["state"] == "open"
        assert kwargs["priority"] == "high"
        assert kwargs["repairable"] is True


class TestGetIssue:
    def test_404_when_missing(self, fake_repo) -> None:
        issues_repo, _jobs, app = fake_repo
        issues_repo.get_issue.return_value = None
        client = TestClient(app)
        resp = client.get(f"/v1/issues/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_returns_issue_with_actions(self, fake_repo) -> None:
        issues_repo, _jobs, app = fake_repo
        issue = _issue_row()
        issues_repo.get_issue.return_value = issue
        issues_repo.list_actions_for_issue.return_value = [_action_row()]
        client = TestClient(app)
        resp = client.get(f"/v1/issues/{issue.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["fingerprint"] == "f" * 32
        assert len(body["actions"]) == 1
        assert body["actions"][0]["action_type"] == "run_repair"


class TestSyncIssues:
    def test_sync_enqueues_worker_job(self, fake_repo) -> None:
        _issues, _jobs, app = fake_repo
        client = TestClient(app)
        resp = client.post(
            "/v1/issues/sync",
            json={"org_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "queued"
        app.state.queue.enqueue_job.assert_awaited_once()
        args = app.state.queue.enqueue_job.call_args.args
        assert args[0] == "sync_external_issues"


class TestRunRepairFromIssue:
    def test_404_when_missing(self, fake_repo) -> None:
        issues_repo, _jobs, app = fake_repo
        issues_repo.get_issue.return_value = None
        client = TestClient(app)
        resp = client.post(
            f"/v1/issues/{uuid.uuid4()}/run-repair",
            json={"actor": "ruslan@selfrepair.dev"},
        )
        assert resp.status_code == 404

    def test_409_when_not_repairable(self, fake_repo) -> None:
        # security-class issues never auto-repair — must be 409, not 200.
        issues_repo, _jobs, app = fake_repo
        issues_repo.get_issue.return_value = _issue_row(
            repairable=False, repair_class="security"
        )
        client = TestClient(app)
        resp = client.post(
            f"/v1/issues/{uuid.uuid4()}/run-repair",
            json={"actor": "ruslan@selfrepair.dev"},
        )
        assert resp.status_code == 409
        assert "security" in resp.json()["detail"]

    def test_creates_job_and_action_and_enqueues(self, fake_repo) -> None:
        issues_repo, jobs_repo, app = fake_repo
        issue = _issue_row(repairable=True)
        issues_repo.get_issue.return_value = issue
        job = _job_row()
        jobs_repo.create.return_value = job
        action = _action_row(job_id=job.id)
        issues_repo.record_action.return_value = action

        client = TestClient(app)
        resp = client.post(
            f"/v1/issues/{issue.id}/run-repair",
            json={"actor": "ruslan@selfrepair.dev"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["job_id"] == str(job.id)
        assert body["action_id"] == str(action.id)

        # job enqueued for the worker
        app.state.queue.enqueue_job.assert_awaited_once()
        args = app.state.queue.enqueue_job.call_args.args
        assert args[0] == "process_job"
        assert args[1] == str(job.id)

        # action carries the issue context as payload (the run_repair seam)
        kwargs = issues_repo.record_action.call_args.kwargs
        assert kwargs["action_type"] is ExternalIssueActionType.RUN_REPAIR
        assert kwargs["job_id"] == job.id
        assert kwargs["payload"]["provider"] == "github"
        assert kwargs["payload"]["issue_title"]


class TestTriage:
    def test_triage_records_completed_action(self, fake_repo) -> None:
        issues_repo, _jobs, app = fake_repo
        issue = _issue_row()
        issues_repo.get_issue.return_value = issue
        action = _action_row()
        issues_repo.record_action.return_value = action

        client = TestClient(app)
        resp = client.post(
            f"/v1/issues/{issue.id}/triage",
            json={"actor": "ops@selfrepair.dev", "note": "needs human"},
        )
        assert resp.status_code == 200
        kwargs = issues_repo.record_action.call_args.kwargs
        assert kwargs["action_type"] is ExternalIssueActionType.TRIAGE
        assert kwargs["action_status"] == "completed"
        assert kwargs["payload"] == {"note": "needs human"}

    def test_triage_404_when_missing(self, fake_repo) -> None:
        issues_repo, _jobs, app = fake_repo
        issues_repo.get_issue.return_value = None
        client = TestClient(app)
        resp = client.post(
            f"/v1/issues/{uuid.uuid4()}/triage",
            json={"actor": "ops"},
        )
        assert resp.status_code == 404


class TestComment:
    def test_comment_queues_action(self, fake_repo) -> None:
        issues_repo, _jobs, app = fake_repo
        issue = _issue_row()
        issues_repo.get_issue.return_value = issue
        action = _action_row()
        issues_repo.record_action.return_value = action

        client = TestClient(app)
        resp = client.post(
            f"/v1/issues/{issue.id}/comment",
            json={"actor": "ops", "body": "ack — repair queued"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        kwargs = issues_repo.record_action.call_args.kwargs
        assert kwargs["action_type"] is ExternalIssueActionType.COMMENT
        assert kwargs["action_status"] == "queued"
        assert kwargs["payload"] == {"body": "ack — repair queued"}
        # worker dispatched
        app.state.queue.enqueue_job.assert_awaited_once()
        args = app.state.queue.enqueue_job.call_args.args
        assert args[0] == "post_external_issue_comment"

    def test_comment_rejects_empty_body(self, fake_repo) -> None:
        _issues, _jobs, app = fake_repo
        client = TestClient(app)
        resp = client.post(
            f"/v1/issues/{uuid.uuid4()}/comment",
            json={"actor": "ops", "body": ""},
        )
        assert resp.status_code == 422


class TestSuppress:
    def test_suppress_flips_repairable(self, fake_repo) -> None:
        issues_repo, _jobs, app = fake_repo
        issue = _issue_row(repairable=True)
        issues_repo.get_issue.return_value = issue
        action = _action_row()
        issues_repo.record_action.return_value = action

        client = TestClient(app)
        resp = client.post(
            f"/v1/issues/{issue.id}/suppress",
            json={"actor": "ops", "reason": "duplicate"},
        )
        assert resp.status_code == 200
        # mutation on the row visible to the caller
        assert issue.repairable is False
        kwargs = issues_repo.record_action.call_args.kwargs
        assert kwargs["action_type"] is ExternalIssueActionType.SUPPRESS
        assert kwargs["action_status"] == "completed"
        assert kwargs["payload"] == {"reason": "duplicate"}
