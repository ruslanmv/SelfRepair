"""Offline tests for the GitPilot coder client."""
from __future__ import annotations

from typing import Any

import httpx

from selfrepair.coders.gitpilot_client import GitPilotClient, RepairResponse

SAMPLE_PLAN: dict[str, Any] = {
    "client_id": "agent-matrix",
    "workspace_id": "ws-1",
    "task_id": "task-abc",
    "repo_url": "https://example.com/repo.git",
    "branch": "main",
    "mode": "dry_run",
    "health_score": 70,
    "issues": [
        {"id": "missing-license", "severity": "medium", "description": "x", "recommended_action": "y"}
    ],
    "allowed_paths": ["LICENSE", "pyproject.toml"],
    "forbidden_paths": [".env"],
    "coder": {"provider": "gitpilot", "model": "code-coder"},
    "sandbox": {"provider": "matrixlab", "profile": "python-repair", "required": True},
}


def test_repair_parses_response(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            json={
                "status": "dry_run",
                "risk_level": "medium",
                "patch_preview": "--- a/LICENSE\n+++ b/LICENSE",
                "changed_files": ["LICENSE"],
                "review": {"approved": False},
                "sandbox_result": {"status": "passed"},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = GitPilotClient(base_url="http://gitpilot.test")
    resp = client.repair(SAMPLE_PLAN, dry_run=True)

    assert captured["url"] == "http://gitpilot.test/repair"
    assert captured["json"]["mode"] == "dry_run"
    assert captured["json"]["task_id"] == "task-abc"
    assert isinstance(resp, RepairResponse)
    assert resp.status == "dry_run"
    assert resp.risk_level == "medium"
    assert resp.changed_files == ["LICENSE"]
    assert resp.stubbed is False


def test_repair_degrades_to_stub_when_unreachable(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "post", boom)

    client = GitPilotClient(base_url="http://localhost:9000")
    resp = client.repair(SAMPLE_PLAN, dry_run=True)

    assert resp.stubbed is True
    assert resp.status == "dry_run"
    # The stub mirrors allowed_paths from the plan as the changed files.
    assert resp.changed_files == ["LICENSE", "pyproject.toml"]


def test_repair_parses_real_gitpilot_response(monkeypatch) -> None:
    """GitPilot's real shape: review is a STRING, changed_files are objects,
    status is one of ok|blocked|error|needs_approval."""

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        return httpx.Response(
            200,
            json={
                "task_id": "task-abc",
                "status": "ok",
                "mode": "dry_run",
                "risk_level": "low",
                "patch_preview": "--- a/tests/test_health.py\n+++ b/tests/test_health.py",
                "changed_files": [
                    {"path": "tests/test_health.py", "change_type": "added"},
                    {"path": "LICENSE", "change_type": "modified"},
                ],
                "review": "Looks safe. Risk: low. Adds a health smoke test.",
                "sandbox_result": None,
                "pr_url": None,
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = GitPilotClient(base_url="http://gitpilot.test")
    resp = client.repair(SAMPLE_PLAN, dry_run=True)

    assert isinstance(resp, RepairResponse)
    assert resp.status == "ok"
    assert resp.risk_level == "low"
    # review string accepted without crashing
    assert isinstance(resp.review, str)
    assert "health" in resp.review.lower()
    # changed_files normalized to a list of path strings
    assert resp.changed_files == ["tests/test_health.py", "LICENSE"]
    # detailed view preserves change_type
    assert resp.changed_files_detailed[0] == {
        "path": "tests/test_health.py",
        "change_type": "added",
    }
    # sandbox_result None coerced to empty dict (never crashes)
    assert resp.sandbox_result == {}
    assert resp.stubbed is False


def test_repair_status_values_do_not_crash(monkeypatch) -> None:
    for status in ("ok", "blocked", "error", "needs_approval"):
        def fake_post(url, json=None, headers=None, timeout=None, _s=status):  # noqa: A002
            return httpx.Response(
                200,
                json={
                    "status": _s,
                    "review": "verdict text",
                    "changed_files": [{"path": "a.py", "change_type": "modified"}],
                },
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        resp = GitPilotClient(base_url="http://gitpilot.test").repair(
            SAMPLE_PLAN, dry_run=True
        )
        assert resp.status == status
        assert resp.changed_files == ["a.py"]


def test_available_false_when_unreachable(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", boom)
    assert GitPilotClient().available() is False
