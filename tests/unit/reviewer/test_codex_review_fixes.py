"""Regression tests for the Codex review of ruslanmv/SelfRepair#7.

1. Pull-request diffs are pinned to the event revision (test_production_io).
2. Deep Agents tools only see redacted snapshots (test_deepagents_and_remediation).
3. The engine deadline returns on time and engines run off the event loop.
4. Repository config only overrides fields it sets.
5. The announced check run is completed, not duplicated, including on failure.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Any

import pytest

from selfrepair.config.repo_config import ReviewerConfig
from selfrepair.reviewer.diff import parse_unified_diff
from selfrepair.reviewer.engines.deepagents_engine import _invoke
from selfrepair.reviewer.publishers import GitHubHttpPublisher
from selfrepair.reviewer.schemas import ReviewEvent, ReviewReport, RunRecord
from selfrepair.reviewer.service import StaticDiffProvider, review_change
from selfrepair.reviewer.settings import resolve_reviewer_config
from tests.unit.reviewer.conftest import ORG, REPO, VULN_DIFF, binding, store_with_repo

# ── 3. deadline and event loop ────────────────────────────────────────


class _StalledAgent:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.release = threading.Event()

    def invoke(self, *_args: Any, **_kwargs: Any) -> dict:
        self.release.wait(self.seconds)
        return {}


def test_invoke_returns_at_the_deadline_not_when_the_call_finishes() -> None:
    agent = _StalledAgent(seconds=10)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        _invoke(agent, "review", timeout_seconds=1)
    elapsed = time.monotonic() - started
    agent.release.set()
    assert elapsed < 3, f"deadline overran: {elapsed:.1f}s"


def test_invoke_propagates_agent_errors() -> None:
    class Broken:
        def invoke(self, *_a: Any, **_k: Any) -> dict:
            raise ValueError("bad model")

    with pytest.raises(ValueError, match="bad model"):
        _invoke(Broken(), "review", timeout_seconds=5)


class _SlowEngine:
    name = "deepagents"

    def review(self, event: ReviewEvent, diff: Any, config: ReviewerConfig) -> ReviewReport:
        del event, diff, config
        time.sleep(0.6)  # a blocking model call
        return ReviewReport(summary="ok", findings=[], engine="deepagents")


def _event(head: str = "b") -> ReviewEvent:
    return ReviewEvent(
        provider="github",
        kind="push",
        delivery_id=f"d-{head}",
        repo_full_name="octo/demo",
        branch="main",
        ref="refs/heads/main",
        base_sha="a" * 40,
        head_sha=head * 40,
        installation_id=99,
    )


@pytest.mark.asyncio
async def test_a_blocking_engine_does_not_block_the_event_loop() -> None:
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    from selfrepair.reviewer.publishers import RecordingPublisher

    task = asyncio.create_task(ticker())
    try:
        await review_change(
            store=store_with_repo(),
            repo=binding(),
            event=_event(),
            config=ReviewerConfig.model_validate({"enabled": True, "engine": "deepagents"}),
            diff_provider=StaticDiffProvider(parse_unified_diff(VULN_DIFF)),
            engine=_SlowEngine(),
            publisher=RecordingPublisher(),
        )
    finally:
        task.cancel()
    assert ticks >= 5, f"event loop was blocked (ticks={ticks})"


# ── 4. settings layering ──────────────────────────────────────────────


def test_repo_file_only_overrides_the_fields_it_sets() -> None:
    org = {"engine": "deepagents", "review": {"block_on": ["critical"]}}
    yaml_text = "version: 1\nreviewer:\n  enabled: true\n"
    config = resolve_reviewer_config(config_yaml=yaml_text, org_settings=org, repo_settings=None)
    assert config.enabled is True
    assert config.engine == "deepagents"
    assert config.review.block_on == ["critical"]


def test_no_repo_file_keeps_org_settings() -> None:
    org = {"enabled": True, "engine": "deepagents"}
    config = resolve_reviewer_config(config_yaml=None, org_settings=org, repo_settings=None)
    assert config.enabled is True and config.engine == "deepagents"


def test_repo_file_is_still_validated() -> None:
    bad = "version: 1\nreviewer:\n  remediation:\n    auto_merge: true\n"
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        resolve_reviewer_config(config_yaml=bad, org_settings=None, repo_settings=None)


def test_api_override_stores_only_what_was_set() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from selfrepair.api.main import build_app

    store = store_with_repo(config_yaml=None)
    app = build_app()
    app.state.review_store = store
    client = TestClient(app)
    headers = {"X-SelfRepair-Org-Id": str(ORG)}
    assert client.put(
        "/v1/review-settings",
        headers=headers,
        json={"config": {"engine": "deepagents", "review": {"block_on": ["critical"]}}},
    ).status_code == 200
    assert client.put(
        f"/v1/repos/{REPO}/review-settings", headers=headers, json={"config": {"enabled": True}}
    ).status_code == 200
    assert store.repo_settings[(ORG, REPO)] == {"enabled": True}
    effective = client.get(f"/v1/repos/{REPO}/review-settings", headers=headers).json()["config"]
    assert effective["enabled"] is True
    assert effective["engine"] == "deepagents"
    assert effective["review"]["block_on"] == ["critical"]
    org_view = client.get("/v1/review-settings", headers=headers).json()["config"]
    assert org_view["engine"] == "deepagents"


# ── 5. one check run per review ───────────────────────────────────────


class _Response:
    def __init__(self, status: int, body: Any) -> None:
        self.status_code = status
        self._body = body
        self.headers: dict[str, str] = {}
        self.text = ""

    def json(self) -> Any:
        return self._body


class _GitHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    async def post(self, url: str, json: dict, headers: dict) -> _Response:  # noqa: A002
        self.calls.append(("POST", url, json))
        return _Response(201, {"id": 77 if url.endswith("/check-runs") else 5})

    async def patch(self, url: str, json: dict, headers: dict) -> _Response:  # noqa: A002
        self.calls.append(("PATCH", url, json))
        return _Response(200, {"id": 77})


def _run() -> RunRecord:
    return RunRecord(
        id=uuid.uuid4(),
        org_id=ORG,
        repo_id=REPO,
        provider="github",
        event_type="push",
        base_sha="a" * 40,
        head_sha="b" * 40,
        engine="deterministic",
        policy_version="1",
        status="running",
    )


@pytest.mark.asyncio
async def test_publish_completes_the_announced_check() -> None:
    github = _GitHub()
    publisher = GitHubHttpPublisher(github, token="ghs_x")
    run, event = _run(), _event()
    await publisher.announce(event=event, run=run)
    results = await publisher.publish(
        event=event,
        run=run,
        findings=[],
        conclusion="success",
        summary="clean",
        already_published=set(),
    )
    check_posts = [c for c in github.calls if c[0] == "POST" and c[1].endswith("/check-runs")]
    patches = [c for c in github.calls if c[0] == "PATCH"]
    assert len(check_posts) == 1, "a second check run was created"
    assert len(patches) == 1 and patches[0][1].endswith("/check-runs/77")
    assert patches[0][2]["status"] == "completed"
    assert patches[0][2]["conclusion"] == "success"
    assert "head_sha" not in patches[0][2]
    check = next(item for item in results if item["kind"] == "check")
    assert check["status"] == "published" and check["external_id"] == "77"


@pytest.mark.asyncio
async def test_publish_without_announce_still_creates_one_check() -> None:
    github = _GitHub()
    await GitHubHttpPublisher(github, token="ghs_x").publish(
        event=_event(),
        run=_run(),
        findings=[],
        conclusion="success",
        summary="clean",
        already_published=set(),
    )
    assert [c[0] for c in github.calls if "check-runs" in c[1]] == ["POST"]


class _BrokenProvider:
    async def collect(self, event: Any, repo: Any) -> Any:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_a_failed_review_gives_the_announced_check_a_terminal_result() -> None:
    github = _GitHub()
    store = store_with_repo()
    outcome, run = await review_change(
        store=store,
        repo=binding(),
        event=_event(),
        config=ReviewerConfig.model_validate({"enabled": True}),
        diff_provider=_BrokenProvider(),
        engine=None,
        publisher=GitHubHttpPublisher(github, token="ghs_x"),
    )
    patches = [c for c in github.calls if c[0] == "PATCH"]
    assert len(patches) == 1, github.calls
    assert patches[0][2]["status"] == "completed"
    assert patches[0][2]["conclusion"] == "action_required"
    assert run is not None and run.conclusion == "action_required"
    del outcome
