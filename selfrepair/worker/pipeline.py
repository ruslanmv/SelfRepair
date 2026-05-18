"""Repair pipeline.

The pipeline maps each active JobState to a stage handler. The Arq worker
calls `run_pipeline_step()` on each tick; the step looks up the handler for
the job's current state, runs it, and the state machine handles the
transition + audit row.

This decouples "what to do at each stage" (handlers) from "drive state
forward" (the pipeline runner) and makes both unit-testable.

After every successful transition the pipeline publishes the just-recorded
`job_event` row to Redis pub/sub so any number of SSE clients can tail the
run in real time. Publish failures are logged but never bubble up — SSE is
a UX nicety, not a correctness gate.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import JobEvent
from selfrepair.persistence.repositories import JobsRepository
from selfrepair.state.machine import JobState

logger = logging.getLogger(__name__)


@dataclass
class StageContext:
    """Inputs handed to each stage handler."""

    job_id: uuid.UUID
    org_id: uuid.UUID
    repo_id: uuid.UUID
    state: JobState
    session: AsyncSession
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageResult:
    """What the stage decided. The pipeline applies the transition."""

    next_state: JobState
    message: str = ""
    payload: dict[str, Any] | None = None


StageHandler = Callable[[StageContext], Awaitable[StageResult]]


class RepairPipeline:
    def __init__(self) -> None:
        self._handlers: dict[JobState, StageHandler] = {}

    def register(self, state: JobState, handler: StageHandler) -> None:
        self._handlers[state] = handler

    def has_handler(self, state: JobState) -> bool:
        return state in self._handlers

    async def step(self, ctx: StageContext) -> StageResult:
        handler = self._handlers.get(ctx.state)
        if handler is None:
            raise LookupError(
                f"no handler registered for state {ctx.state.value}"
            )
        return await handler(ctx)


async def _publish_latest_event(
    session: AsyncSession, job_id: uuid.UUID
) -> None:
    """Publish the most recent `job_event` row for `job_id` to pub/sub.

    Called after the session commits so subscribers only ever see
    durable events. Best-effort: any failure is swallowed.
    """
    try:
        event = (
            await session.execute(
                select(JobEvent)
                .where(JobEvent.job_id == job_id)
                .order_by(JobEvent.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if event is None:
            return
        payload = {
            "id": event.id,
            "job_id": str(event.job_id),
            "ts": event.ts.isoformat(),
            "stage": (
                event.stage.value
                if hasattr(event.stage, "value")
                else event.stage
            ),
            "level": event.level,
            "message": event.message,
            "payload": event.payload,
        }
        # Imported lazily so pipeline tests don't need redis installed.
        from selfrepair.api.events import publish_job_event

        await publish_job_event(job_id, payload)
    except Exception:  # pragma: no cover - best effort
        logger.debug("event pub/sub publish failed", exc_info=True)


async def run_pipeline_step(
    pipeline: RepairPipeline,
    *,
    session: AsyncSession,
    job_id: uuid.UUID,
    extra: dict[str, Any] | None = None,
) -> JobState:
    """Run a single pipeline step and persist the result.

    Returns the new state. The caller decides whether to re-enqueue the job
    based on whether the new state is paused or terminal.

    On unhandled exception the job is moved to ESCALATED so the audit log
    captures the failure and the worker can move on. Programming errors
    (LookupError for a missing handler) are surfaced.
    """
    jobs = JobsRepository(session)
    job = await jobs.get(job_id)
    if job is None:
        raise LookupError(f"job {job_id} not found")

    ctx = StageContext(
        job_id=job_id,
        org_id=job.org_id,
        repo_id=job.repo_id,
        state=job.state,
        session=session,
        extra=extra or {},
    )

    try:
        result = await pipeline.step(ctx)
    except LookupError:
        await session.rollback()
        raise
    except Exception as exc:
        logger.exception(
            "pipeline step failed for job %s in state %s",
            job_id, job.state.value,
        )
        await session.rollback()
        async with session.begin():
            await JobsRepository(session).fail(
                job_id, error_kind=type(exc).__name__, message=str(exc)
            )
        await _publish_latest_event(session, job_id)
        return JobState.ESCALATED

    await jobs.advance(
        job_id, result.next_state,
        message=result.message, payload=result.payload,
    )
    await session.commit()
    await _publish_latest_event(session, job_id)
    return result.next_state
