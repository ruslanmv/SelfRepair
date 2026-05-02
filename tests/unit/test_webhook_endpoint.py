"""FastAPI webhook endpoint tests.

Runs against an in-process app with a mocked Arq queue. The lifespan is not
entered (no `with` around TestClient) so we don't try to connect to a real
Redis during unit tests.
"""
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("arq")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")

    from selfrepair.api.main import build_app

    app = build_app()
    # Lifespan would set this to a real Arq pool. Override before TestClient
    # so we don't try to connect to Redis during unit tests.
    app.state.queue = MagicMock()
    app.state.queue.enqueue_job = AsyncMock()
    return app


@pytest.fixture
def client(app):
    # No `with`: we don't want lifespan to run, since it would replace our
    # mock queue with a real one.
    return TestClient(app)


def _sign(body: bytes, secret: str = "test-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestHealth:
    def test_healthz_returns_ok(self, client) -> None:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_readyz_returns_ready(self, client) -> None:
        resp = client.get("/readyz")
        assert resp.status_code == 200


class TestGitHubWebhook:
    def test_rejects_bad_signature(self, client) -> None:
        body = b'{"action": "x"}'
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "abc",
                "X-Hub-Signature-256": "sha256=" + "0" * 64,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401

    def test_ping_returns_pong(self, client) -> None:
        body = b"{}"
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "abc",
                "X-Hub-Signature-256": _sign(body),
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "pong"}

    def test_push_event_is_enqueued(self, client, app) -> None:
        body = b'{"repository": {"full_name": "octo/hello"}}'
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "abc",
                "X-Hub-Signature-256": _sign(body),
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
        app.state.queue.enqueue_job.assert_awaited_once()
        args = app.state.queue.enqueue_job.call_args.args
        assert args[0] == "ingest_webhook"
        assert args[1] == "push"
        assert args[2] == "abc"
        assert args[3]["repository"]["full_name"] == "octo/hello"

    def test_unhandled_event_is_acknowledged(self, client, app) -> None:
        body = b"{}"
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "release",  # not in handled set
                "X-GitHub-Delivery": "abc",
                "X-Hub-Signature-256": _sign(body),
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        app.state.queue.enqueue_job.assert_not_awaited()

    def test_missing_signature_header_is_rejected(self, client) -> None:
        body = b"{}"
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "abc",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401
