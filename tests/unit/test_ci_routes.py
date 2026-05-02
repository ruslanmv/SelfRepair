"""FastAPI CI Guardian read endpoints.

The route layer's contract is shape, not SQL: given a repository that
returns a row (or None), it must serialise it correctly and translate
404 / 400 cases into HTTP responses.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from selfrepair.api.routes import ci as ci_route  # noqa: E402
from selfrepair.persistence.models import CIFailureStatus  # noqa: E402


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")

    from selfrepair.api.main import build_app

    app = build_app()
    app.state.queue = MagicMock()
    app.state.queue.enqueue_job = AsyncMock()
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def fake_ci_repo(monkeypatch):
    """Replace CIRepository so route handlers receive a programmable double."""
    repo = MagicMock()
    repo.get_workflow_run = AsyncMock()
    repo.list_jobs_for_run = AsyncMock(return_value=[])
    repo.get_failure = AsyncMock()
    repo.list_failures_for_repo = AsyncMock(return_value=[])
    repo.list_open_failures_for_org = AsyncMock(return_value=[])
    monkeypatch.setattr(ci_route, "CIRepository", lambda _session: repo)

    # Replace the session dependency with a no-op async generator.
    async def _fake_session():
        yield MagicMock()

    from selfrepair.api.main import build_app

    app = build_app()
    app.dependency_overrides[ci_route._session] = _fake_session
    app.state.queue = MagicMock()
    return repo, app


def _run_row(**overrides):
    base = dict(
        id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        github_run_id=42,
        run_attempt=1,
        workflow_name="CI",
        workflow_path=".github/workflows/ci.yml",
        head_sha="abc",
        head_branch="main",
        event="push",
        status="completed",
        conclusion="failure",
        html_url="https://github.com/octo/x/actions/runs/42",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        last_event="completed",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _failure_row(**overrides):
    base = dict(
        id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        workflow_run_id=uuid.uuid4(),
        workflow_job_id=None,
        fingerprint="f" * 32,
        failure_class="test_failure",
        severity="medium",
        status=CIFailureStatus.OPEN,
        auto_action=None,
        confidence=None,
        occurrence_count=1,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        resolved_at=None,
        kill_switched=False,
        redacted_secret_count=0,
        last_error_signature="AssertionError",
        policy_decision={"action": "NONE"},
        repair_pr_url=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestGetRun:
    def test_returns_404_when_missing(self, fake_ci_repo) -> None:
        repo, app = fake_ci_repo
        repo.get_workflow_run.return_value = None
        client = TestClient(app)
        resp = client.get(f"/v1/ci/runs/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_returns_run_with_jobs(self, fake_ci_repo) -> None:
        repo, app = fake_ci_repo
        run = _run_row()
        repo.get_workflow_run.return_value = run
        client = TestClient(app)
        resp = client.get(f"/v1/ci/runs/{run.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["github_run_id"] == 42
        assert body["jobs"] == []


class TestListRepoFailures:
    def test_status_filter_validation(self, fake_ci_repo) -> None:
        _repo, app = fake_ci_repo
        client = TestClient(app)
        resp = client.get(
            f"/v1/ci/repos/{uuid.uuid4()}/failures?status=not_a_status"
        )
        assert resp.status_code == 400

    def test_returns_failures_serialised(self, fake_ci_repo) -> None:
        repo, app = fake_ci_repo
        repo.list_failures_for_repo.return_value = [_failure_row()]
        client = TestClient(app)
        resp = client.get(f"/v1/ci/repos/{uuid.uuid4()}/failures")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        item = body["items"][0]
        assert item["failure_class"] == "test_failure"
        assert item["status"] == "open"
        assert item["policy_decision"] == {"action": "NONE"}


class TestGetFailure:
    def test_returns_404_when_missing(self, fake_ci_repo) -> None:
        repo, app = fake_ci_repo
        repo.get_failure.return_value = None
        client = TestClient(app)
        resp = client.get(f"/v1/ci/failures/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_returns_failure(self, fake_ci_repo) -> None:
        repo, app = fake_ci_repo
        f = _failure_row()
        repo.get_failure.return_value = f
        client = TestClient(app)
        resp = client.get(f"/v1/ci/failures/{f.id}")
        assert resp.status_code == 200
        assert resp.json()["fingerprint"] == "f" * 32


class TestListOpenFailures:
    def test_lists_open_for_org(self, fake_ci_repo) -> None:
        repo, app = fake_ci_repo
        repo.list_open_failures_for_org.return_value = [_failure_row()]
        client = TestClient(app)
        resp = client.get(f"/v1/ci/orgs/{uuid.uuid4()}/failures/open")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
