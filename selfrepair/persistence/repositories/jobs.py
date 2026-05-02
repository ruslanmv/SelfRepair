"""Repository for jobs and job events."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import Job, JobEvent, JobTrigger
from selfrepair.state.machine import JobState, assert_transition

_TERMINAL_STATES: frozenset[JobState] = frozenset(
    {JobState.COMPLETED, JobState.MERGED, JobState.CLOSED, JobState.STALE}
)

_ACTIVE_STATES: tuple[JobState, ...] = (
    JobState.QUEUED,
    JobState.CLONING,
    JobState.ANALYZING,
    JobState.SCANNING,
    JobState.PLANNING,
    JobState.REPAIRING,
    JobState.VALIDATING,
    JobState.PUBLISHING,
    JobState.AWAITING_REVIEW,
)


class JobsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        trigger: JobTrigger,
    ) -> Job:
        job = Job(
            org_id=org_id,
            repo_id=repo_id,
            trigger=trigger,
            state=JobState.QUEUED,
        )
        self._session.add(job)
        await self._session.flush()
        await self._record_event(job.id, JobState.QUEUED, message="job queued")
        return job

    async def get(self, job_id: uuid.UUID) -> Job | None:
        return await self._session.get(Job, job_id)

    async def advance(
        self,
        job_id: uuid.UUID,
        target: JobState,
        *,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> Job:
        """Validate and apply a state transition.

        Raises `InvalidTransition` if the new state is not allowed from the
        current one. The transition and the matching event row are committed
        together by the caller.
        """
        job = await self.get(job_id)
        if job is None:
            raise LookupError(f"job {job_id} not found")
        assert_transition(job.state, target)
        job.state = target
        if target in _TERMINAL_STATES:
            job.finished_at = datetime.now(UTC)
        await self._record_event(job_id, target, message=message, payload=payload)
        return job

    async def fail(
        self, job_id: uuid.UUID, *, error_kind: str, message: str
    ) -> Job:
        """Move the job to ESCALATED with an error_kind tag.

        Used for unhandled exceptions — ESCALATED is reachable from any active
        state, so this never raises InvalidTransition.
        """
        job = await self.get(job_id)
        if job is None:
            raise LookupError(f"job {job_id} not found")
        assert_transition(job.state, JobState.ESCALATED)
        job.state = JobState.ESCALATED
        job.error_kind = error_kind
        job.finished_at = datetime.now(UTC)
        await self._record_event(
            job_id, JobState.ESCALATED, level="error", message=message
        )
        return job

    async def list_active_for_repo(self, repo_id: uuid.UUID) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.repo_id == repo_id, Job.state.in_(_ACTIVE_STATES))
            .order_by(Job.started_at)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def _record_event(
        self,
        job_id: uuid.UUID,
        stage: JobState,
        *,
        level: str = "info",
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = JobEvent(
            job_id=job_id,
            stage=stage,
            level=level,
            message=message,
            payload=payload,
        )
        self._session.add(event)
