"""Webhook dispatch: opt-in, dedupe, malformed payloads, and worker wiring."""
from __future__ import annotations

import uuid

import pytest

from selfrepair.reviewer.diff import parse_unified_diff
from selfrepair.reviewer.dispatcher import (
    dispatch_github_review_event,
    dispatch_gitlab_review_event,
)
from selfrepair.reviewer.service import StaticDiffProvider
from selfrepair.worker.main import build_pipeline, ingest_gitlab_webhook, ingest_webhook
from tests.unit.reviewer.conftest import VULN_DIFF, store_with_repo

pytest.importorskip("pydantic")


def _push(delivery: str = "d1", *, branch: str = "main", before: str = "a" * 40, after: str = "b" * 40, deleted: bool = False, sender: str = "octocat") -> dict:
    after_sha = "0" * 40 if deleted else after
    return {
        "ref": f"refs/heads/{branch}",
        "before": before,
        "after": after_sha,
        "forced": False,
        "compare": "https://github.com/octo/demo/compare/a...b",
        "commits": [
            {"id": after, "message": "one"},
            {"id": "c" * 40, "message": "two"},
        ] if not deleted else [],
        "repository": {"full_name": "octo/demo", "default_branch": "main"},
        "installation": {"id": 99},
        "sender": {"login": sender, "type": "User"},
    }


def _ctx(store, diff: str | None = VULN_DIFF):
    files = parse_unified_diff(diff) if diff else []
    return {
        "review_store": store,
        "diff_provider": StaticDiffProvider(files),
        "job_try": 1,
    }


@pytest.mark.asyncio
async def test_push_creates_one_run() -> None:
    store = store_with_repo()
    outcome = await dispatch_github_review_event(
        ctx=_ctx(store), event_type="push", delivery_id="d1", payload=_push()
    )
    assert outcome == "reviewed"
    assert len(store.runs) == 1
    run = next(iter(store.runs.values()))
    assert run.head_sha == "b" * 40
    assert len(run.commit_shas) == 2
    assert run.conclusion == "failure"
    assert any(item.severity == "critical" or item.severity == "high" for item in store.findings[run.id])


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_create_a_second_run() -> None:
    store = store_with_repo()
    ctx = _ctx(store)
    await dispatch_github_review_event(ctx=ctx, event_type="push", delivery_id="d1", payload=_push())
    outcome = await dispatch_github_review_event(
        ctx=ctx, event_type="push", delivery_id="d1", payload=_push()
    )
    assert outcome == "duplicate"
    assert len(store.runs) == 1


@pytest.mark.asyncio
async def test_same_change_set_from_a_new_delivery_reuses_the_run() -> None:
    store = store_with_repo()
    ctx = _ctx(store)
    await dispatch_github_review_event(ctx=ctx, event_type="push", delivery_id="d1", payload=_push())
    outcome = await dispatch_github_review_event(
        ctx=ctx, event_type="push", delivery_id="d2", payload=_push()
    )
    assert outcome == "reviewed"
    assert len(store.runs) == 1


@pytest.mark.asyncio
async def test_unknown_repo_is_ignored() -> None:
    store = store_with_repo()
    payload = _push()
    payload["repository"]["full_name"] = "other/repo"
    outcome = await dispatch_github_review_event(
        ctx=_ctx(store), event_type="push", delivery_id="d1", payload=payload
    )
    assert outcome == "ignored"
    assert store.runs == {}


@pytest.mark.asyncio
async def test_malformed_payload_is_ignored() -> None:
    store = store_with_repo()
    outcome = await dispatch_github_review_event(
        ctx=_ctx(store), event_type="push", delivery_id="d1", payload={"zen": "no repo"}
    )
    assert outcome == "ignored"


@pytest.mark.asyncio
async def test_disabled_monitoring_creates_no_run() -> None:
    store = store_with_repo(config_yaml="version: 1\nreviewer:\n  enabled: false\n")
    outcome = await dispatch_github_review_event(
        ctx=_ctx(store), event_type="push", delivery_id="d1", payload=_push()
    )
    assert outcome == "ignored"
    assert store.runs == {}


@pytest.mark.asyncio
async def test_unmonitored_branch_is_ignored() -> None:
    store = store_with_repo()
    outcome = await dispatch_github_review_event(
        ctx=_ctx(store),
        event_type="push",
        delivery_id="d1",
        payload=_push(branch="feature/wip"),
    )
    assert outcome == "ignored"


@pytest.mark.asyncio
async def test_deleted_branch_does_not_analyze() -> None:
    store = store_with_repo()
    outcome = await dispatch_github_review_event(
        ctx=_ctx(store), event_type="push", delivery_id="d1", payload=_push(deleted=True)
    )
    assert outcome == "reviewed"
    run = next(iter(store.runs.values()))
    assert run.status == "skipped"
    assert run.conclusion == "neutral"
    assert store.findings[run.id] == []


@pytest.mark.asyncio
async def test_selfrepair_branch_does_not_recurse() -> None:
    store = store_with_repo()
    outcome = await dispatch_github_review_event(
        ctx=_ctx(store),
        event_type="push",
        delivery_id="d1",
        payload=_push(branch="selfrepair/secret/20261102"),
    )
    assert outcome == "ignored"
    assert store.runs == {}


@pytest.mark.asyncio
async def test_force_push_is_one_run_and_supersedes_the_previous_head() -> None:
    store = store_with_repo()
    ctx = _ctx(store)
    await dispatch_github_review_event(ctx=ctx, event_type="push", delivery_id="d1", payload=_push())
    payload = _push(delivery="d2", before="b" * 40, after="d" * 40)
    payload["forced"] = True
    outcome = await dispatch_github_review_event(
        ctx=ctx, event_type="push", delivery_id="d2", payload=payload
    )
    assert outcome == "reviewed"
    assert len(store.runs) == 2
    older = next(run for run in store.runs.values() if run.head_sha == "b" * 40)
    newer = next(run for run in store.runs.values() if run.head_sha == "d" * 40)
    assert older.status == "superseded"
    assert newer.forced is True
    assert newer.conclusion == "failure"


@pytest.mark.asyncio
async def test_ambiguous_installation_is_ignored() -> None:
    from selfrepair.reviewer.store import MemoryReviewStore
    from tests.unit.reviewer.conftest import binding

    other = binding(org_id=uuid.uuid4(), repo_id=uuid.uuid4(), installation_id=99)
    first = binding()
    store = MemoryReviewStore(repos=[first, other])
    outcome = await dispatch_github_review_event(
        ctx=_ctx(store), event_type="push", delivery_id="d1", payload=_push()
    )
    assert outcome == "ignored"


@pytest.mark.asyncio
async def test_worker_push_uses_the_review_dispatcher() -> None:
    store = store_with_repo()
    outcome = await ingest_webhook(_ctx(store), "push", "d1", _push())
    assert outcome == "reviewed"
    assert len(store.runs) == 1


@pytest.mark.asyncio
async def test_worker_installation_event_stays_log_only() -> None:
    store = store_with_repo()
    outcome = await ingest_webhook(
        _ctx(store),
        "installation",
        "d1",
        {"repository": {"full_name": "octo/demo"}},
    )
    assert outcome == "ingested"
    assert store.runs == {}


@pytest.mark.asyncio
async def test_pull_request_synchronize_reviews_the_head() -> None:
    store = store_with_repo()
    payload = {
        "action": "synchronize",
        "number": 7,
        "pull_request": {
            "number": 7,
            "draft": False,
            "title": "fix",
            "head": {"sha": "b" * 40, "ref": "feature", "repo": {"full_name": "octo/demo"}},
            "base": {"sha": "a" * 40, "ref": "main", "repo": {"full_name": "octo/demo"}},
        },
        "repository": {"full_name": "octo/demo", "default_branch": "main"},
        "installation": {"id": 99},
        "sender": {"login": "octocat", "type": "User"},
    }
    outcome = await dispatch_github_review_event(
        ctx=_ctx(store), event_type="pull_request", delivery_id="pr1", payload=payload
    )
    assert outcome == "reviewed"
    run = next(iter(store.runs.values()))
    assert run.pr_number == 7
    assert run.event_type == "pull_request"
    kinds = [item["kind"] for item in store.publications]
    assert "check" in kinds
    assert "review" in kinds
    review = next(item for item in store.publications if item["kind"] == "review")
    assert review["payload"]["event"] == "COMMENT"


@pytest.mark.asyncio
async def test_gitlab_merge_request_open() -> None:
    store = store_with_repo(provider="gitlab", full_name="group/demo")
    payload = {
        "project": {"id": 5, "path_with_namespace": "group/demo", "default_branch": "main"},
        "user": {"username": "ada"},
        "object_attributes": {
            "id": 10,
            "iid": 3,
            "action": "open",
            "source_branch": "feature",
            "target_branch": "main",
            "title": "change",
            "last_commit": {"id": "b" * 40},
        },
    }
    outcome = await dispatch_gitlab_review_event(
        ctx=_ctx(store), event_type="Merge Request Hook", payload=payload
    )
    assert outcome == "reviewed"
    run = next(iter(store.runs.values()))
    assert run.provider == "gitlab"
    assert run.pr_number == 3


@pytest.mark.asyncio
async def test_worker_gitlab_merge_request_is_not_an_issue() -> None:
    store = store_with_repo(provider="gitlab", full_name="group/demo")
    payload = {
        "project": {"id": 5, "path_with_namespace": "group/demo", "default_branch": "main"},
        "user": {"username": "ada"},
        "object_attributes": {
            "id": 10,
            "iid": 3,
            "action": "update",
            "source_branch": "feature",
            "target_branch": "main",
            "oldrev": "a" * 40,
            "last_commit": {"id": "b" * 40},
        },
    }
    outcome = await ingest_gitlab_webhook(_ctx(store), "Merge Request Hook", payload)
    assert outcome == "reviewed"


def test_repair_pipeline_still_builds() -> None:
    pipeline = build_pipeline()
    assert pipeline.has_handler(__import__("selfrepair.state.machine", fromlist=["JobState"]).JobState.QUEUED)
