"""Offline tests for the MatrixLab validation client."""
from __future__ import annotations

from typing import Any

import httpx

from selfrepair.validation.matrixlab_client import MatrixLabClient, RunResult


def test_validate_patch_builds_request_and_parses(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            json={
                "run_id": "run-1",
                "status": "passed",
                "exit_code": 0,
                "stdout": "ok",
                "stderr": "",
                "duration_ms": 1234,
                "artifacts": [{"name": "log", "url": "http://x/log"}],
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = MatrixLabClient(base_url="http://matrixlab.test")
    result = client.validate_patch(
        client_id="agent-matrix",
        workspace_id="ws-1",
        repo_url="https://example.com/repo.git",
        branch="main",
        profile="python-repair",
    )

    assert captured["url"] == "http://matrixlab.test/repo/validate-patch"
    body = captured["json"]
    assert body["client_id"] == "agent-matrix"
    assert body["workspace_id"] == "ws-1"
    assert body["profile"] == "python-repair"

    assert isinstance(result, RunResult)
    assert result.run_id == "run-1"
    assert result.passed is True
    assert result.duration_ms == 1234
    assert result.artifacts[0]["name"] == "log"


def test_health_false_when_unreachable(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", boom)
    assert MatrixLabClient().health() is False


def test_run_degrades_to_stub_when_unreachable(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "post", boom)

    client = MatrixLabClient(base_url="http://localhost:8765")
    result = client.run(
        client_id="c",
        workspace_id="w",
        repo_url="https://example.com/repo.git",
        branch="main",
        profile="python-repair",
    )
    assert result.stubbed is True
    assert result.status == "skipped"
