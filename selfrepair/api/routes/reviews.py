"""`/v1/reviews` — list, inspect, trigger, and retry code reviews.

Tenancy comes from `CtxDep`. A caller cannot read another organization's
runs. Triggering a review does not approve a pull request or merge anything.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from selfrepair.api.deps import DEFAULT_LIMIT, MAX_LIMIT, CtxDep
from selfrepair.config.repo_config import ReviewerConfig
from selfrepair.reviewer.diff import parse_unified_diff
from selfrepair.reviewer.engines.deterministic import DeterministicReviewEngine
from selfrepair.reviewer.publishers import RecordingPublisher
from selfrepair.reviewer.schemas import ReviewEvent
from selfrepair.reviewer.service import StaticDiffProvider, review_change
from selfrepair.reviewer.settings import resolve_reviewer_config
from selfrepair.reviewer.store import ReviewStore, SqlReviewStore

router = APIRouter(prefix="/v1", tags=["reviews"])


class TriggerReview(BaseModel):
    """Manual review of a pinned SHA range. The diff is supplied by the caller."""

    repo_full_name: str = Field(min_length=3, max_length=255)
    provider: str = "github"
    branch: str = "main"
    base_sha: str = Field(min_length=7, max_length=64)
    head_sha: str = Field(min_length=7, max_length=64)
    unified_diff: str = ""
    pr_number: int | None = None


class RemediationBody(BaseModel):
    """An explicit request to hand accepted findings to GitPilot `POST /repair`.

    `approve` records the caller as the human approver. Without it the task
    is a dry run. `auto_merge` exists only so a request for it is refused.
    """

    model_config = {"extra": "forbid"}

    fingerprints: list[str] = Field(min_length=1, max_length=50)
    allowed_paths: list[str] | None = None
    approve: bool = False
    auto_merge: bool = False


class ReviewSettingsBody(BaseModel):
    """A partial or full reviewer config. Unknown keys are rejected."""

    config: dict[str, Any]


def _store(request: Request) -> ReviewStore:
    override = getattr(request.app.state, "review_store", None)
    if override is not None:
        return override
    from selfrepair.api.deps import get_app_sessionmaker

    return SqlReviewStore(get_app_sessionmaker())


def _public_run(run: Any) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "org_id": str(run.org_id),
        "repo_id": str(run.repo_id),
        "provider": run.provider,
        "event_type": run.event_type,
        "base_sha": run.base_sha,
        "head_sha": run.head_sha,
        "ref": run.ref,
        "pr_number": run.pr_number,
        "engine": run.engine,
        "model_id": run.model_id,
        "policy_version": run.policy_version,
        "status": run.status,
        "conclusion": run.conclusion,
        "summary": run.summary,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/reviews")
async def list_reviews(
    request: Request,
    ctx: CtxDep,
    repo_id: uuid.UUID | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict[str, Any]:
    """List review runs for the caller's organization."""
    store = _store(request)
    rows = await store.list_runs(org_id=ctx.org_id, repo_id=repo_id, limit=limit)
    return {"items": [_public_run(row) for row in rows]}


@router.get("/reviews/{review_id}")
async def get_review(request: Request, ctx: CtxDep, review_id: uuid.UUID) -> dict[str, Any]:
    """Return one review run. A run from another organization is a 404."""
    run = await _owned_run(request, ctx.org_id, review_id)
    return _public_run(run)


@router.get("/reviews/{review_id}/findings")
async def get_findings(request: Request, ctx: CtxDep, review_id: uuid.UUID) -> dict[str, Any]:
    """Return validated findings for one review run."""
    await _owned_run(request, ctx.org_id, review_id)
    findings = await _store(request).list_findings(review_id)
    return {
        "items": [
            {
                "fingerprint": item.fingerprint,
                "category": item.category,
                "severity": item.severity,
                "confidence": item.confidence,
                "file_path": item.file_path,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "title": item.title,
                "description": item.description,
                "evidence": item.evidence,
                "suggested_fix": item.suggested_fix,
                "source": item.source,
                "validation_state": item.validation_state,
            }
            for item in findings
        ]
    }


@router.post("/reviews/trigger", status_code=status.HTTP_201_CREATED)
async def trigger_review(
    request: Request, ctx: CtxDep, body: TriggerReview
) -> dict[str, Any]:
    """Review a caller-supplied diff for a repository in this organization.

    This does not publish to GitHub unless the process has a review publisher
    configured. The default publisher records the payload only.
    """
    store = _store(request)
    repo = await store.resolve_repo(
        provider=body.provider, full_name=body.repo_full_name, installation_id=None
    )
    if repo is None or repo.ambiguous or repo.org_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="repository not found")
    org_settings, repo_settings = await store.settings_for(
        org_id=repo.org_id, repo_id=repo.repo_id
    )
    config = resolve_reviewer_config(
        config_yaml=repo.config_yaml,
        org_settings=org_settings,
        repo_settings=repo_settings,
    )
    config = config.model_copy(update={"enabled": True, "engine": "deterministic"})
    event = ReviewEvent(
        provider="github" if body.provider == "github" else "gitlab",
        kind="pull_request" if body.pr_number else "push",
        delivery_id=f"manual-{uuid.uuid4()}",
        repo_full_name=body.repo_full_name,
        branch=body.branch,
        base_sha=body.base_sha,
        head_sha=body.head_sha,
        pr_number=body.pr_number,
        ref=f"refs/heads/{body.branch}",
    )
    files = parse_unified_diff(body.unified_diff) if body.unified_diff else []
    publisher = getattr(request.app.state, "review_publisher", None) or RecordingPublisher()
    outcome, run = await review_change(
        store=store,
        repo=repo,
        event=event,
        config=config,
        diff_provider=StaticDiffProvider(files),
        engine=DeterministicReviewEngine(),
        publisher=publisher,
    )
    if run is None:
        raise HTTPException(status_code=400, detail=outcome)
    return {"outcome": outcome, "review": _public_run(run)}


@router.post("/reviews/{review_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_review(request: Request, ctx: CtxDep, review_id: uuid.UUID) -> dict[str, Any]:
    """Mark an incomplete run queued again. Does not invent a new conclusion."""
    store = _store(request)
    run = await _owned_run(request, ctx.org_id, review_id)
    if run.status not in {"incomplete", "failed", "queued"}:
        raise HTTPException(status_code=409, detail="review is not retryable")
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        updated = await store.update_run(
            run.id, status="queued", conclusion=None, error=None, completed_at=None
        )
        await queue.enqueue_job("retry_review", str(review_id))
        return {"outcome": "queued", "review": _public_run(updated)}
    from selfrepair.reviewer.dispatcher import rerun_review

    ctx: dict[str, Any] = {"review_store": store, "job_try": 2}
    diff_provider = getattr(request.app.state, "review_diff_provider", None)
    publisher = getattr(request.app.state, "review_publisher", None)
    if diff_provider is not None:
        ctx["diff_provider"] = diff_provider
    if publisher is not None:
        ctx["review_publisher"] = publisher
    app_github = getattr(request.app.state, "github_app", None)
    if app_github is not None:
        ctx["github_app"] = app_github
    outcome = await rerun_review(ctx, str(review_id))
    refreshed = await store.get_run(review_id)
    return {"outcome": outcome, "review": _public_run(refreshed or run)}


@router.get("/reviews/{review_id}/remediations")
async def list_remediations(
    request: Request, ctx: CtxDep, review_id: uuid.UUID
) -> dict[str, Any]:
    """Remediation tasks requested for one review run."""
    from selfrepair.reviewer.remediation import list_tasks, public_task

    run = await _owned_run(request, ctx.org_id, review_id)
    return {"items": [public_task(item) for item in list_tasks(run)]}


@router.post("/reviews/{review_id}/remediations", status_code=status.HTTP_202_ACCEPTED)
async def create_remediation(
    request: Request, ctx: CtxDep, review_id: uuid.UUID, body: RemediationBody
) -> dict[str, Any]:
    """Send accepted findings of this run to GitPilot as one repair task.

    Refused for forks, disabled remediation, unknown findings, paths outside
    the finding files, empty path lists, and `auto_merge`. SelfRepair does not
    approve, merge, or push the result; a GitPilot draft PR gets its own review.
    """
    from selfrepair.reviewer.remediation import (
        RemediationRefused,
        create_task,
        execute_task,
        gitpilot_client_from_env,
        public_task,
    )

    store = _store(request)
    run = await _owned_run(request, ctx.org_id, review_id)
    config = await _config_for_run(store, run)
    try:
        task = await create_task(
            store=store,
            run=run,
            config=config,
            fingerprints=body.fingerprints,
            allowed_paths=body.allowed_paths,
            approve=body.approve,
            requested_by=ctx.actor,
            auto_merge=body.auto_merge,
        )
    except RemediationRefused as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        await queue.enqueue_job("remediate_review", str(review_id), task["id"])
        return {"outcome": "queued", "task": public_task(task)}
    client = getattr(request.app.state, "gitpilot_client", None) or gitpilot_client_from_env()
    done = await execute_task(store=store, review_id=review_id, task_id=task["id"], client=client)
    return {"outcome": done["status"], "task": public_task(done)}


@router.get("/repos/{repo_id}/review-settings")
async def get_repo_settings(
    request: Request, ctx: CtxDep, repo_id: uuid.UUID
) -> dict[str, Any]:
    """Return the effective reviewer config for one repository."""
    store = _store(request)
    org_settings, repo_settings = await store.settings_for(org_id=ctx.org_id, repo_id=repo_id)
    # The repo file is not on this request. API layers still merge.
    config = resolve_reviewer_config(
        config_yaml=None, org_settings=org_settings, repo_settings=repo_settings
    )
    return {"repo_id": str(repo_id), "config": config.model_dump()}


@router.put("/repos/{repo_id}/review-settings")
async def put_repo_settings(
    request: Request, ctx: CtxDep, repo_id: uuid.UUID, body: ReviewSettingsBody
) -> dict[str, Any]:
    """Replace the per-repository reviewer override. `enabled` stays opt-in."""
    config = _validate_settings(body.config)
    saved = await _store(request).put_settings(
        org_id=ctx.org_id, repo_id=repo_id, config=config.model_dump()
    )
    return {"repo_id": str(repo_id), "config": saved}


@router.get("/review-settings")
async def get_org_settings(request: Request, ctx: CtxDep) -> dict[str, Any]:
    """Return the organization default reviewer config."""
    org_settings, _repo = await _store(request).settings_for(
        org_id=ctx.org_id, repo_id=uuid.UUID(int=0)
    )
    config = resolve_reviewer_config(
        config_yaml=None, org_settings=org_settings, repo_settings=None
    )
    return {"config": config.model_dump()}


@router.put("/review-settings")
async def put_org_settings(
    request: Request, ctx: CtxDep, body: ReviewSettingsBody
) -> dict[str, Any]:
    """Replace the organization default. Repositories can still override it."""
    config = _validate_settings(body.config)
    saved = await _store(request).put_settings(
        org_id=ctx.org_id, repo_id=None, config=config.model_dump()
    )
    return {"config": saved}


async def _owned_run(request: Request, org_id: uuid.UUID, review_id: uuid.UUID) -> Any:
    run = await _store(request).get_run(review_id)
    if run is None or run.org_id != org_id:
        raise HTTPException(status_code=404, detail="review not found")
    return run


async def _config_for_run(store: ReviewStore, run: Any) -> ReviewerConfig:
    """The effective reviewer config for a run's repository, file included."""
    meta = run.metadata or {}
    installation = meta.get("installation_id")
    repo = await store.resolve_repo(
        provider=run.provider,
        full_name=str(meta.get("repo_full_name") or ""),
        installation_id=installation if isinstance(installation, int) else None,
    )
    config_yaml = None
    if repo is not None and not repo.ambiguous and repo.repo_id == run.repo_id:
        config_yaml = repo.config_yaml
    org_settings, repo_settings = await store.settings_for(
        org_id=run.org_id, repo_id=run.repo_id
    )
    return resolve_reviewer_config(
        config_yaml=config_yaml, org_settings=org_settings, repo_settings=repo_settings
    )


def _validate_settings(raw: dict[str, Any]) -> ReviewerConfig:
    try:
        return ReviewerConfig.model_validate(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
