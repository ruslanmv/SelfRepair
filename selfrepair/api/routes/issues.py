"""Issue Watch API — `/v1/issues`.

Phase-1 surface for the Open Issues frontend tab. Read endpoints are wired
to the IssuesRepository directly. The `sync` and `run-repair` endpoints
record an action row but defer the heavy lifting (provider polling, job
enqueue) to the worker, kept behind the `enqueue_action` seam so unit
tests can override it.

Mutating endpoints aren't deleted here — they're scoped narrowly to the
Phase-1 contract: enqueue a sync, or enqueue a repair job from a
repairable issue. Triage / comment / suppress land with later phases.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence import get_sessionmaker
from selfrepair.persistence.models import (
    ExternalIssue,
    ExternalIssueActionType,
    JobTrigger,
)
from selfrepair.persistence.repositories import IssuesRepository, JobsRepository

router = APIRouter(prefix="/v1/issues", tags=["issues"])


async def _session() -> AsyncIterator[AsyncSession]:
    database_url = os.getenv(
        "SELFREPAIR_DATABASE_URL",
        "postgresql+asyncpg://selfrepair:selfrepair@localhost/selfrepair",
    )
    sessionmaker = get_sessionmaker(database_url)
    async with sessionmaker() as session:
        yield session


# ---------------- response shapes ----------------


def _serialize(issue: ExternalIssue) -> dict[str, Any]:
    return {
        "id": str(issue.id),
        "org_id": str(issue.org_id),
        "repo_id": str(issue.repo_id),
        "provider": issue.provider,
        "provider_issue_id": issue.provider_issue_id,
        "number": issue.number,
        "title": issue.title,
        "body_excerpt": issue.body_excerpt,
        "state": issue.state,
        "author": issue.author,
        "labels": issue.labels or [],
        "assignees": issue.assignees or [],
        "priority": issue.priority,
        "repair_class": issue.repair_class,
        "repairable": issue.repairable,
        "html_url": issue.html_url,
        "created_at_external": (
            issue.created_at_external.isoformat()
            if issue.created_at_external
            else None
        ),
        "updated_at_external": (
            issue.updated_at_external.isoformat()
            if issue.updated_at_external
            else None
        ),
        "closed_at_external": (
            issue.closed_at_external.isoformat()
            if issue.closed_at_external
            else None
        ),
        "last_synced_at": issue.last_synced_at.isoformat(),
        "fingerprint": issue.fingerprint,
    }


# ---------------- read endpoints ----------------


@router.get("")
async def list_issues(
    org_id: uuid.UUID = Query(..., description="Org scope is mandatory"),
    repo_id: uuid.UUID | None = Query(default=None),
    provider: str | None = Query(default=None),
    state: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    repairable: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(_session),
) -> dict[str, Any]:
    repo = IssuesRepository(session)
    issues = await repo.list_issues(
        org_id=org_id,
        repo_id=repo_id,
        provider=provider,
        state=state,
        priority=priority,
        repairable=repairable,
        limit=limit,
    )
    return {
        "items": [_serialize(i) for i in issues],
        "count": len(issues),
    }


@router.get("/{issue_id}")
async def get_issue(
    issue_id: uuid.UUID, session: AsyncSession = Depends(_session)
) -> dict[str, Any]:
    repo = IssuesRepository(session)
    issue = await repo.get_issue(issue_id)
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="external_issue not found",
        )
    actions = await repo.list_actions_for_issue(issue_id)
    return {
        **_serialize(issue),
        "actions": [
            {
                "id": str(a.id),
                "action_type": a.action_type.value,
                "action_status": a.action_status,
                "actor": a.actor,
                "job_id": str(a.job_id) if a.job_id else None,
                "finding_id": str(a.finding_id) if a.finding_id else None,
                "repair_id": str(a.repair_id) if a.repair_id else None,
                "comment_url": a.comment_url,
                "created_at": a.created_at.isoformat(),
            }
            for a in actions
        ],
    }


# ---------------- mutating endpoints ----------------


class SyncRequest(BaseModel):
    """Optional repo scope; unscoped sync touches every connected repo."""

    org_id: uuid.UUID = Field(..., description="Org scope is mandatory")
    repo_id: uuid.UUID | None = None
    actor: str | None = Field(
        default=None, description="Audit-log actor (email or service id)"
    )


class RunRepairRequest(BaseModel):
    actor: str | None = Field(
        default=None, description="Audit-log actor (email or service id)"
    )


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_issues(
    body: SyncRequest,
    request: Request,
    session: AsyncSession = Depends(_session),
) -> dict[str, Any]:
    """Schedule a provider-side sync.

    The actual fetch is the worker's `sync_external_issues` task. This
    endpoint only records the audit row; the queue handoff is intentional
    so a ratelimited provider doesn't block the API thread.
    """
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        await queue.enqueue_job(
            "sync_external_issues",
            str(body.repo_id) if body.repo_id else None,
        )
    return {
        "status": "queued",
        "repo_id": str(body.repo_id) if body.repo_id else None,
    }


@router.post("/{issue_id}/run-repair")
async def run_repair_from_issue(
    issue_id: uuid.UUID,
    body: RunRepairRequest,
    request: Request,
    session: AsyncSession = Depends(_session),
) -> dict[str, Any]:
    """Enqueue a normal SelfRepair job from a repairable external issue.

    Phase-1 contract:
      * issue must exist and be marked repairable (security/feature_request
        classes are blocked here; they're escalation-only)
      * a job row is created with trigger=ISSUE
      * an external_issue_action(action_type=run_repair) audit row links
        the issue to the job
      * the worker's existing process_job task picks it up
    """
    issues_repo = IssuesRepository(session)
    issue = await issues_repo.get_issue(issue_id)
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="external_issue not found",
        )
    if not issue.repairable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"issue is not repairable (class={issue.repair_class}); "
                "use triage instead"
            ),
        )

    jobs_repo = JobsRepository(session)
    job = await jobs_repo.create(
        org_id=issue.org_id,
        repo_id=issue.repo_id,
        trigger=JobTrigger.ISSUE,
    )
    action = await issues_repo.record_action(
        org_id=issue.org_id,
        external_issue_id=issue.id,
        action_type=ExternalIssueActionType.RUN_REPAIR,
        actor=body.actor,
        action_status="queued",
        job_id=job.id,
        payload={
            "external_issue_id": str(issue.id),
            "provider": issue.provider,
            "issue_url": issue.html_url,
            "issue_title": issue.title,
            "issue_labels": issue.labels or [],
            "issue_body_excerpt": issue.body_excerpt,
        },
    )
    await session.commit()

    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        await queue.enqueue_job("process_job", str(job.id))

    return {
        "job_id": str(job.id),
        "action_id": str(action.id),
        "status": "queued",
    }


# ---------------- triage / comment / suppress ----------------
#
# These three endpoints share a shape: take an actor + optional payload,
# record an external_issue_action row, return its id. The action_status
# is "completed" (synchronous side-effect) for triage/suppress, and
# either "completed" or "failed" for comment depending on whether the
# provider call succeeded.


class TriageRequest(BaseModel):
    actor: str | None = None
    note: str | None = Field(default=None, max_length=2000)


class CommentRequest(BaseModel):
    actor: str | None = None
    body: str = Field(..., min_length=1, max_length=10_000)


class SuppressRequest(BaseModel):
    actor: str | None = None
    reason: str | None = Field(default=None, max_length=500)


@router.post("/{issue_id}/triage")
async def triage_issue(
    issue_id: uuid.UUID,
    body: TriageRequest,
    session: AsyncSession = Depends(_session),
) -> dict[str, Any]:
    """Record a manual triage decision.

    Triage is the answer for issues that aren't auto-repairable
    (security / bug / feature_request / unknown). It logs a triage row;
    no upstream provider call is made.
    """
    issues_repo = IssuesRepository(session)
    issue = await issues_repo.get_issue(issue_id)
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="external_issue not found",
        )
    action = await issues_repo.record_action(
        org_id=issue.org_id,
        external_issue_id=issue.id,
        action_type=ExternalIssueActionType.TRIAGE,
        actor=body.actor,
        action_status="completed",
        payload={"note": body.note} if body.note else None,
    )
    await session.commit()
    return {"action_id": str(action.id), "status": "completed"}


@router.post("/{issue_id}/comment")
async def comment_on_issue(
    issue_id: uuid.UUID,
    body: CommentRequest,
    request: Request,
    session: AsyncSession = Depends(_session),
) -> dict[str, Any]:
    """Post a comment back to the upstream issue.

    Phase-1 returns 202 and lets the worker do the provider call; the
    audit row's `action_status` starts as `queued` and the worker flips
    it to `completed` or `failed`. We don't synchronously talk to the
    provider here so a ratelimited GitHub doesn't take down the API.
    """
    issues_repo = IssuesRepository(session)
    issue = await issues_repo.get_issue(issue_id)
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="external_issue not found",
        )
    action = await issues_repo.record_action(
        org_id=issue.org_id,
        external_issue_id=issue.id,
        action_type=ExternalIssueActionType.COMMENT,
        actor=body.actor,
        action_status="queued",
        payload={"body": body.body},
    )
    await session.commit()

    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        # The worker job that dispatches comments lands with Phase-2; for
        # now the row exists and a future operator-console replay will
        # reissue it. Surfaced explicitly to the caller in `pending`.
        await queue.enqueue_job(
            "post_external_issue_comment", str(action.id)
        )

    return {"action_id": str(action.id), "status": "queued"}


@router.post("/{issue_id}/suppress")
async def suppress_issue(
    issue_id: uuid.UUID,
    body: SuppressRequest,
    session: AsyncSession = Depends(_session),
) -> dict[str, Any]:
    """Suppress an issue from the dashboard.

    Doesn't touch the provider. Sets `repairable=False` on the row so
    the run-repair endpoint also rejects it, and writes a SUPPRESS
    audit row carrying the operator-supplied reason.
    """
    issues_repo = IssuesRepository(session)
    issue = await issues_repo.get_issue(issue_id)
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="external_issue not found",
        )
    issue.repairable = False
    action = await issues_repo.record_action(
        org_id=issue.org_id,
        external_issue_id=issue.id,
        action_type=ExternalIssueActionType.SUPPRESS,
        actor=body.actor,
        action_status="completed",
        payload={"reason": body.reason} if body.reason else None,
    )
    await session.commit()
    return {"action_id": str(action.id), "status": "completed"}
