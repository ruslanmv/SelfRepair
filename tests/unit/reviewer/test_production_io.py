"""Production I/O: installation tokens, live publishers, and retries.

These tests use fake transports. They do not call GitHub, GitLab, or a model.
"""
from __future__ import annotations

import uuid

import pytest

from selfrepair.reviewer.credentials import credential_status, github_token_for
from selfrepair.reviewer.diff import parse_unified_diff
from selfrepair.reviewer.diff_provider import GitHubCompareProvider, GitLabCompareProvider
from selfrepair.reviewer.dispatcher import dispatch_github_review_event, rerun_review
from selfrepair.reviewer.publishers import GitLabHttpPublisher
from selfrepair.reviewer.runtime import build_review_io
from selfrepair.reviewer.schemas import ReviewEvent
from selfrepair.reviewer.service import StaticDiffProvider
from tests.unit.reviewer.conftest import CLEAN_DIFF, VULN_DIFF, binding, store_with_repo

pytest.importorskip("pydantic")


class _Response:
    def __init__(self, status: int, body: object) -> None:
        self.status_code = status
        self._body = body
        self.headers: dict[str, str] = {}
        self.text = ""

    def json(self) -> object:
        return self._body


class _Transport:
    def __init__(self, body: object, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.calls: list[tuple[str, str]] = []

    async def get(self, url: str, headers: dict[str, str]) -> _Response:
        self.calls.append(("GET", url))
        assert "PRIVATE-TOKEN" in headers or headers.get("Authorization", "").startswith("Bearer ")
        return _Response(self.status, self.body)

    async def post(self, url: str, json: dict, headers: dict[str, str]) -> _Response:  # noqa: A002
        self.calls.append(("POST", url))
        assert "token-value" not in url
        return _Response(self.status, {"id": 42})


def _push() -> dict:
    return {
        "ref": "refs/heads/main",
        "before": "a" * 40,
        "after": "b" * 40,
        "forced": False,
        "commits": [{"id": "b" * 40, "message": "one"}],
        "repository": {"full_name": "octo/demo", "default_branch": "main"},
        "installation": {"id": 99},
        "sender": {"login": "octocat", "type": "User"},
    }


@pytest.mark.asyncio
async def test_installation_token_is_preferred_over_a_static_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFREPAIR_GITHUB_TOKEN", "static-token")

    class App:
        async def installation_token(self, installation_id: int) -> str:
            assert installation_id == 99
            return "ghs_installation"

    token = await github_token_for(99, app=App())  # type: ignore[arg-type]
    assert token == "ghs_installation"
    fallback = await github_token_for(None, app=None)
    assert fallback == "static-token"


def test_credential_status_does_not_include_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\\nsecret")
    monkeypatch.setenv("SELFREPAIR_GITHUB_TOKEN", "ghp_should_not_appear")
    status = credential_status()
    assert status["github_app"] is True
    assert status["github_token"] is True
    rendered = str(status)
    assert "ghp_should_not_appear" not in rendered
    assert "BEGIN PRIVATE KEY" not in rendered


@pytest.mark.asyncio
async def test_missing_credentials_do_not_record_a_successful_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SELFREPAIR_GITHUB_TOKEN",
        "GITHUB_TOKEN",
        "GITHUB_APP_ID",
        "SELFREPAIR_GITHUB_APP_ID",
        "GITHUB_APP_PRIVATE_KEY",
        "SELFREPAIR_GITHUB_APP_PRIVATE_KEY",
        "GITHUB_APP_PRIVATE_KEY_PATH",
        "SELFREPAIR_GITHUB_APP_PRIVATE_KEY_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    store = store_with_repo()
    outcome = await dispatch_github_review_event(
        ctx={"review_store": store, "job_try": 1},
        event_type="push",
        delivery_id="d-live",
        payload=_push(),
    )
    assert outcome == "incomplete"
    run = next(iter(store.runs.values()))
    assert run.conclusion == "action_required"
    assert store.publications
    assert all(item["status"] == "unpublished" for item in store.publications)


class _Routes:
    """GET transport that answers per URL suffix and records the calls."""

    def __init__(self, routes: dict[str, tuple[int, object]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    async def get(self, url: str, headers: dict[str, str]) -> _Response:
        self.calls.append(url)
        for suffix, (status, body) in self.routes.items():
            if url.split("?")[0].endswith(suffix):
                return _Response(status, body)
        return _Response(404, {"message": "Not Found"})


_PATCH_FILE = {
    "filename": "app.py",
    "status": "modified",
    "patch": "@@ -1 +1,2 @@\n+password = \"supersecretvalue\"\n",
}


def _pr_event() -> ReviewEvent:
    return ReviewEvent(
        provider="github",
        kind="pull_request",
        delivery_id="pr",
        repo_full_name="octo/demo",
        branch="feature",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        from_fork=True,
    )


@pytest.mark.asyncio
async def test_pull_request_diff_is_pinned_to_the_event_revision() -> None:
    """`/pulls/{n}/files` is the PR *now*; compare by SHA is the event's revision."""
    transport = _Routes({f"/compare/{'a' * 40}...{'b' * 40}": (200, {"files": [_PATCH_FILE]})})
    diff = await GitHubCompareProvider("ghs_test", transport).collect(_pr_event(), binding())
    assert len(transport.calls) == 1
    assert "/compare/" in transport.calls[0] and "/pulls/" not in transport.calls[0]
    assert diff.source == "github-compare"
    assert diff.files[0].path == "app.py"


@pytest.mark.asyncio
async def test_pull_files_fallback_only_when_the_head_has_not_moved() -> None:
    same_head = _Routes(
        {
            "/pulls/7": (200, {"head": {"sha": "b" * 40}}),
            "/pulls/7/files": (200, [_PATCH_FILE]),
        }
    )
    diff = await GitHubCompareProvider("ghs_test", same_head).collect(_pr_event(), binding())
    assert diff.source == "github-pull-files"
    assert diff.files[0].path == "app.py" and diff.error is None

    moved = _Routes(
        {
            "/pulls/7": (200, {"head": {"sha": "c" * 40}}),
            "/pulls/7/files": (200, [_PATCH_FILE]),
        }
    )
    diff = await GitHubCompareProvider("ghs_test", moved).collect(_pr_event(), binding())
    assert not diff.files
    assert "head moved" in (diff.error or "")
    assert not any(url.split("?")[0].endswith("/files") for url in moved.calls)


@pytest.mark.asyncio
async def test_gitlab_compare_and_note_use_the_project_api() -> None:
    transport = _Transport(
        {
            "diffs": [
                {
                    "old_path": "app.py",
                    "new_path": "app.py",
                    "diff": "@@ -1 +1,2 @@\n+token = \"ghp_abcdefghijklmnopqrstuvwxyz0123456789\"\n",
                }
            ]
        }
    )
    event = ReviewEvent(
        provider="gitlab",
        kind="merge_request",
        delivery_id="mr",
        repo_full_name="group/demo",
        project_id=5,
        branch="feature",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=3,
    )
    diff = await GitLabCompareProvider("glpat", transport).collect(event, binding())
    assert "/projects/5/repository/compare" in transport.calls[0][1]
    assert diff.files[0].lines
    publisher = GitLabHttpPublisher(transport, token="glpat")
    from selfrepair.reviewer.schemas import RunRecord
    from tests.unit.reviewer.conftest import ORG, REPO

    run = RunRecord(
        id=uuid.uuid4(),
        org_id=ORG,
        repo_id=REPO,
        provider="gitlab",
        event_type="merge_request",
        base_sha="a" * 40,
        head_sha="b" * 40,
        engine="deterministic",
        policy_version="1",
        status="running",
    )
    sent = await publisher.publish(
        event=event,
        run=run,
        findings=[],
        conclusion="success",
        summary="clean",
        already_published=set(),
    )
    urls = [url for _method, url in transport.calls if _method == "POST"]
    assert any("/statuses/" in url for url in urls)
    assert any("/merge_requests/3/notes" in url for url in urls)
    assert all(item["status"] == "published" for item in sent)


@pytest.mark.asyncio
async def test_runtime_mints_and_builds_a_github_publisher() -> None:
    class App:
        async def installation_token(self, installation_id: int) -> str:
            assert installation_id == 99
            return "ghs_minted"

    event = ReviewEvent(
        provider="github",
        kind="push",
        delivery_id="d",
        repo_full_name="octo/demo",
        installation_id=99,
        branch="main",
        base_sha="a" * 40,
        head_sha="b" * 40,
    )
    provider, publisher = await build_review_io(event, binding(installation_id=99), app=App())  # type: ignore[arg-type]
    assert provider._token == "ghs_minted"
    assert publisher._token == "ghs_minted"


@pytest.mark.asyncio
async def test_retry_reruns_the_same_change_set() -> None:
    store = store_with_repo()
    await dispatch_github_review_event(
        ctx={"review_store": store, "job_try": 1},
        event_type="push",
        delivery_id="d-retry",
        payload=_push(),
    )
    run = next(iter(store.runs.values()))
    assert run.status == "incomplete"
    files = parse_unified_diff(VULN_DIFF)
    outcome = await rerun_review(
        {
            "review_store": store,
            "job_try": 2,
            "diff_provider": StaticDiffProvider(files),
            "review_publisher": __import__(
                "selfrepair.reviewer.publishers", fromlist=["RecordingPublisher"]
            ).RecordingPublisher(),
        },
        str(run.id),
    )
    assert outcome == "reviewed"
    refreshed = store.runs[run.id]
    assert refreshed.conclusion == "failure"
    assert refreshed.head_sha == "b" * 40


def test_review_api_retry_without_a_queue_reruns(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from selfrepair.api.main import build_app
    from tests.unit.reviewer.conftest import ORG

    monkeypatch.delenv("SELFREPAIR_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    store = store_with_repo()
    app = build_app()
    app.state.review_store = store
    client = TestClient(app)
    headers = {"X-SelfRepair-Org-Id": str(ORG)}
    created = client.post(
        "/v1/reviews/trigger",
        headers=headers,
        json={
            "repo_full_name": "octo/demo",
            "branch": "main",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "unified_diff": "",
        },
    )
    assert created.status_code == 201, created.text
    review_id = created.json()["review"]["id"]
    assert created.json()["review"]["conclusion"] == "action_required"
    app.state.review_diff_provider = StaticDiffProvider(parse_unified_diff(CLEAN_DIFF))
    retried = client.post(f"/v1/reviews/{review_id}/retry", headers=headers)
    assert retried.status_code == 202, retried.text
    assert retried.json()["review"]["conclusion"] == "success"
