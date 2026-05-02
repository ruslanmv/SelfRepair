"""CI Guardian read-only API for the dashboard.

Phase 1 surfaces the rows the dispatcher writes — workflow runs, jobs, and
deduplicated failures — so the operator can verify CI Guardian is observing
correctly before any auto-rerun or auto-repair is enabled.

All endpoints are read-only. Mutating endpoints (suppress, escalate, force
repair) come with the operator console in a later phase.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence import get_sessionmaker
from selfrepair.persistence.models import CIFailureStatus
from selfrepair.persistence.repositories import CIRepository

router = APIRouter(prefix="/v1/ci", tags=["ci"])


async def _session() -> AsyncIterator[AsyncSession]:
    database_url = os.getenv(
        "SELFREPAIR_DATABASE_URL",
        "postgresql+asyncpg://selfrepair:selfrepair@localhost/selfrepair",
    )
    sessionmaker = get_sessionmaker(database_url)
    async with sessionmaker() as session:
        yield session


def _serialize_run(run: Any) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "repo_id": str(run.repo_id),
        "github_run_id": run.github_run_id,
        "run_attempt": run.run_attempt,
        "workflow_name": run.workflow_name,
        "workflow_path": run.workflow_path,
        "head_sha": run.head_sha,
        "head_branch": run.head_branch,
        "event": run.event,
        "status": run.status,
        "conclusion": run.conclusion,
        "html_url": run.html_url,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": (
            run.completed_at.isoformat() if run.completed_at else None
        ),
        "last_event": run.last_event,
    }


def _serialize_job(job: Any) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "workflow_run_id": str(job.workflow_run_id),
        "github_job_id": job.github_job_id,
        "name": job.name,
        "status": job.status,
        "conclusion": job.conclusion,
        "runner_name": job.runner_name,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": (
            job.completed_at.isoformat() if job.completed_at else None
        ),
        "failed_step_name": job.failed_step_name,
        "step_failure_index": job.step_failure_index,
    }


def _serialize_failure(failure: Any) -> dict[str, Any]:
    return {
        "id": str(failure.id),
        "repo_id": str(failure.repo_id),
        "workflow_run_id": str(failure.workflow_run_id),
        "workflow_job_id": (
            str(failure.workflow_job_id) if failure.workflow_job_id else None
        ),
        "fingerprint": failure.fingerprint,
        "failure_class": failure.failure_class,
        "severity": failure.severity,
        "status": failure.status.value,
        "auto_action": failure.auto_action,
        "confidence": (
            float(failure.confidence) if failure.confidence is not None else None
        ),
        "occurrence_count": failure.occurrence_count,
        "first_seen_at": failure.first_seen_at.isoformat(),
        "last_seen_at": failure.last_seen_at.isoformat(),
        "resolved_at": (
            failure.resolved_at.isoformat() if failure.resolved_at else None
        ),
        "kill_switched": failure.kill_switched,
        "redacted_secret_count": failure.redacted_secret_count,
        "last_error_signature": failure.last_error_signature,
        "policy_decision": failure.policy_decision,
        "repair_pr_url": failure.repair_pr_url,
    }


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(_session)
) -> dict[str, Any]:
    repo = CIRepository(session)
    run = await repo.get_workflow_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="workflow run not found"
        )
    jobs = await repo.list_jobs_for_run(run_id)
    return {**_serialize_run(run), "jobs": [_serialize_job(j) for j in jobs]}


@router.get("/repos/{repo_id}/failures")
async def list_repo_failures(
    repo_id: uuid.UUID,
    status_: list[str] | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(_session),
) -> dict[str, Any]:
    repo = CIRepository(session)
    statuses: tuple[CIFailureStatus, ...] | None = None
    if status_:
        try:
            statuses = tuple(CIFailureStatus(s) for s in status_)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid status filter: {exc}",
            ) from exc
    failures = await repo.list_failures_for_repo(
        repo_id, statuses=statuses, limit=limit
    )
    return {
        "items": [_serialize_failure(f) for f in failures],
        "count": len(failures),
    }


@router.get("/failures/{failure_id}")
async def get_failure(
    failure_id: uuid.UUID, session: AsyncSession = Depends(_session)
) -> dict[str, Any]:
    repo = CIRepository(session)
    failure = await repo.get_failure(failure_id)
    if failure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ci failure not found"
        )
    return _serialize_failure(failure)


@router.get("/orgs/{org_id}/failures/open")
async def list_open_failures(
    org_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(_session),
) -> dict[str, Any]:
    repo = CIRepository(session)
    failures = await repo.list_open_failures_for_org(org_id, limit=limit)
    return {
        "items": [_serialize_failure(f) for f in failures],
        "count": len(failures),
    }
