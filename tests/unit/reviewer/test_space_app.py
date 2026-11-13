"""The single-process review bot used on a Hugging Face Space."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from selfrepair.reviewer import space_app
from selfrepair.reviewer.diff import parse_unified_diff
from selfrepair.reviewer.publishers import RecordingPublisher
from selfrepair.reviewer.service import StaticDiffProvider
from tests.unit.reviewer.conftest import VULN_DIFF

SECRET = "whsec-test"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _pr(owner: str = "octo") -> dict[str, Any]:
    repo = {"full_name": f"{owner}/demo", "default_branch": "main"}
    return {
        "action": "opened", "number": 3, "installation": {"id": 5}, "repository": repo,
        "sender": {"login": "ada", "type": "User"},
        "pull_request": {"number": 3, "title": "t", "draft": False,
                         "head": {"sha": "b" * 40, "ref": "feat", "repo": repo},
                         "base": {"sha": "a" * 40, "ref": "main", "repo": repo}},
    }


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("SELFREPAIR_SETUP_TOKEN", raising=False)
    space_app.store.repos.clear()
    space_app.store.runs.clear() if hasattr(space_app.store, "runs") else None
    published = RecordingPublisher()

    async def fake_io(event, repo, *, app=None):
        return StaticDiffProvider(parse_unified_diff(VULN_DIFF)), published

    monkeypatch.setattr("selfrepair.reviewer.runtime.build_review_io", fake_io)
    with TestClient(space_app.app) as c:
        c.published = published  # type: ignore[attr-defined]
        yield c


def _post(c: TestClient, payload: dict[str, Any], event: str = "pull_request", sig: str | None = None):
    body = json.dumps(payload).encode()
    return c.post("/webhooks/github", content=body, headers={
        "X-GitHub-Event": event, "X-GitHub-Delivery": "d-1",
        "X-Hub-Signature-256": sig or _sign(body), "Content-Type": "application/json"})


def test_unsigned_webhooks_are_refused(client) -> None:
    assert _post(client, _pr(), sig="sha256=00").status_code == 401


def test_a_pull_request_is_reviewed_in_codex_style(client) -> None:
    assert _post(client, _pr()).json()["status"] == "accepted"
    kinds = [p["kind"] for p in client.published.sent]
    assert "review" in kinds
    review = next(p for p in client.published.sent if p["kind"] == "review")["body"]
    assert review["body"].startswith("### 💡 SelfRepair Review")
    assert client.get("/healthz").json()["stats"]["reviews"] == 1


def test_owners_outside_the_allow_list_are_ignored(client, monkeypatch) -> None:
    monkeypatch.setenv("SELFREPAIR_ALLOWED_OWNERS", "ruslanmv")
    _post(client, _pr("someone-else"))
    assert client.published.sent == []


def test_setup_is_hidden_without_the_token(client, monkeypatch) -> None:
    assert client.get("/setup").status_code == 404
    monkeypatch.setenv("SELFREPAIR_SETUP_TOKEN", "s3cret")
    monkeypatch.setenv("SPACE_HOST", "demo.hf.space")
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    assert client.get("/setup?token=wrong").status_code == 404
    page = client.get("/setup?token=s3cret").text
    assert "https://github.com/settings/apps/new?state=" in page
    assert "demo.hf.space/webhooks/github" in page
    assert client.get("/setup?token=s3cret&org=bad/name").status_code == 400


def test_health_never_returns_secrets(client) -> None:
    text = client.get("/healthz").text + client.get("/").text
    assert SECRET not in text
