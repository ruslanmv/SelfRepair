"""GitLab webhook endpoint.

Contracts:
  * Missing GITLAB_WEBHOOK_SECRET → 500 (operator misconfig is loud).
  * Bad token → 401.
  * Unknown event type → 200 ignored.
  * Issue Hook with a good token → 200 queued + worker job enqueued.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("arq")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "gl-secret")
    from selfrepair.api.main import build_app

    app = build_app()
    app.state.queue = MagicMock()
    app.state.queue.enqueue_job = AsyncMock()
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestGitLabWebhook:
    def test_missing_secret_returns_500(self, monkeypatch) -> None:
        monkeypatch.delenv("GITLAB_WEBHOOK_SECRET", raising=False)
        from selfrepair.api.main import build_app

        app = build_app()
        app.state.queue = MagicMock()
        client = TestClient(app)
        resp = client.post(
            "/webhooks/gitlab",
            json={},
            headers={
                "X-Gitlab-Event": "Issue Hook",
                "X-Gitlab-Token": "anything",
            },
        )
        assert resp.status_code == 500

    def test_bad_token_returns_401(self, client) -> None:
        resp = client.post(
            "/webhooks/gitlab",
            json={},
            headers={
                "X-Gitlab-Event": "Issue Hook",
                "X-Gitlab-Token": "wrong",
            },
        )
        assert resp.status_code == 401

    def test_unknown_event_type_is_ignored(self, client) -> None:
        resp = client.post(
            "/webhooks/gitlab",
            json={},
            headers={
                "X-Gitlab-Event": "Push Hook",
                "X-Gitlab-Token": "gl-secret",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_issue_hook_is_queued(self, client, app) -> None:
        resp = client.post(
            "/webhooks/gitlab",
            json={
                "object_kind": "issue",
                "project": {"path_with_namespace": "platform/x"},
                "object_attributes": {"id": 1, "iid": 1, "state": "opened"},
            },
            headers={
                "X-Gitlab-Event": "Issue Hook",
                "X-Gitlab-Token": "gl-secret",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["event"] == "Issue Hook"
        app.state.queue.enqueue_job.assert_awaited_once()
        args = app.state.queue.enqueue_job.call_args.args
        assert args[0] == "ingest_gitlab_webhook"
        assert args[1] == "Issue Hook"
