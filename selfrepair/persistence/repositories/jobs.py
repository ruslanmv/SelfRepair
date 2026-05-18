"""Repository for jobs and job events."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import Job, JobEvent, JobTrigger, Repo
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

ACTIVE_STATES = _ACTIVE_STATES  # public re-export for routes that need it


class JobsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --------------------------- writes (worker) ---------------------------

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

    async def advance(
        self,
        job_id: uuid.UUID,
        target: JobState,
        *,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> Job:
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

    # --------------------------- reads (api) -------------------------------

    async def get(self, job_id: uuid.UUID) -> Job | None:
        return await self._session.get(Job, job_id)

    async def get_for_org(
        self, job_id: uuid.UUID, org_id: uuid.UUID
    ) -> Job | None:
        stmt = select(Job).where(Job.id == job_id, Job.org_id == org_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_active_for_repo(self, repo_id: uuid.UUID) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.repo_id == repo_id, Job.state.in_(_ACTIVE_STATES))
            .order_by(Job.started_at)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def list_for_org(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None = None,
        state: JobState | None = None,
        active_only: bool = False,
        limit: int = 50,
        after_started_at: datetime | None = None,
        after_id: uuid.UUID | None = None,
    ) -> list[tuple[Job, Repo]]:
        """Page over jobs joined to their repo.

        Keyset on `(started_at DESC, id DESC)` — the natural "latest
        first" the console renders.
        """
        stmt = (
            select(Job, Repo)
            .join(Repo, Repo.id == Job.repo_id)
            .where(Job.org_id == org_id)
            .order_by(Job.started_at.desc(), Job.id.desc())
            .limit(limit)
        )
        if repo_id is not None:
            stmt = stmt.where(Job.repo_id == repo_id)
        if state is not None:
            stmt = stmt.where(Job.state == state)
        elif active_only:
            stmt = stmt.where(Job.state.in_(_ACTIVE_STATES))
        if after_started_at is not None and after_id is not None:
            stmt = stmt.where(
                or_(
                    Job.started_at < after_started_at,
                    and_(
                        Job.started_at == after_started_at,
                        Job.id < after_id,
                    ),
                )
            )
        rows = (await self._session.execute(stmt)).all()
        return [(j, r) for (j, r) in rows]

    async def list_events(
        self,
        *,
        job_id: uuid.UUID,
        after_id: int | None = None,
        limit: int = 200,
    ) -> list[JobEvent]:
        stmt = (
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(JobEvent.id)
            .limit(limit)
        )
        if after_id is not None:
            stmt = stmt.where(JobEvent.id > after_id)
        return list((await self._session.execute(stmt)).scalars())

    # ---------------------------- internal --------------------------------

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
