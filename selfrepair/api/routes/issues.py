"""Issue Watch API — `/v1/issues`.

Phase-1 surface for the Open Issues frontend tab. Read endpoints are wired
to the IssuesRepository directly. The `sync` and `run-repair` endpoints
record an action row but defer the heavy lifting (provider polling, job
enqueue) to the worker, kept behind the `enqueue_action` seam so unit
tests can override it.

Mutating endpoints aren't deleted here — they're scoped narrowly to the
Phase-1 contract: enqueue a sync, or enqueue a repair job from a
repairable issue. Triage / comment / suppress land with later phases.

Org scope is sourced from `CtxDep` (session cookie / dev header) on the
list endpoint; mutating endpoints still accept an explicit `org_id` in
the body for backward compatibility.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.api.deps import CtxDep, SessionDep
from selfrepair.persistence import get_sessionmaker
from selfrepair.persistence.models import (
    ExternalIssue,
    ExternalIssueActionType,
    JobTrigger,
)
from selfrepair.persistence.repositories import IssuesRepository, JobsRepository

router = APIRouter(prefix="/v1/issues", tags=["issues"])


# Legacy session helper kept for the mutating endpoints; the list endpoint
# uses the shared SessionDep.
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
    ctx: CtxDep,
    session: SessionDep,
    repo_id: uuid.UUID | None = Query(default=None),
    provider: str | None = Query(default=None),
    state: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    repairable: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    repo = IssuesRepository(session)
    issues = await repo.list_issues(
        org_id=ctx.org_id,
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
