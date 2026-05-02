"""Arq worker entrypoint.

Run with::

    arq selfrepair.worker.main.WorkerSettings

Registers two job functions:

- `process_job(job_id)`: drives a job through the state machine until it
  pauses or terminates.
- `ingest_webhook(event_type, delivery_id, payload)`: translates a GitHub
  webhook into job(s); CI events route through `selfrepair.ci.dispatcher`.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from arq.connections import RedisSettings

from selfrepair.persistence import get_sessionmaker
from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import (
    RepairPipeline,
    StageContext,
    StageResult,
    run_pipeline_step,
)
from selfrepair.worker.settings import get_worker_settings
from selfrepair.worker.stages import (
    analyze_stage,
    clone_stage,
    plan_stage,
    publish_stage,
    repair_stage,
    scan_stage,
    validate_stage,
)

logger = logging.getLogger(__name__)

_PAUSED_STATES: frozenset[JobState] = frozenset(
    {
        JobState.AWAITING_REVIEW,
        JobState.COMPLETED,
        JobState.FAILED_VALIDATION,
        JobState.ESCALATED,
        JobState.MERGED,
        JobState.CLOSED,
        JobState.STALE,
    }
)

_CI_EVENTS: frozenset[str] = frozenset(
    {"workflow_run", "workflow_job", "check_run", "check_suite"}
)

_ISSUE_EVENTS: frozenset[str] = frozenset({"issues", "issue_comment"})


async def _kickoff(ctx: StageContext) -> StageResult:
    """Trivial QUEUED → CLONING transition so the worker self-starts."""
    return StageResult(next_state=JobState.CLONING, message="kickoff")


def build_pipeline() -> RepairPipeline:
    """Build the default pipeline. Public so tests can extend or replace stages."""
    pipeline = RepairPipeline()
    pipeline.register(JobState.QUEUED, _kickoff)
    pipeline.register(JobState.CLONING, clone_stage)
    pipeline.register(JobState.ANALYZING, analyze_stage)
    pipeline.register(JobState.SCANNING, scan_stage)
    pipeline.register(JobState.PLANNING, plan_stage)
    pipeline.register(JobState.REPAIRING, repair_stage)
    pipeline.register(JobState.VALIDATING, validate_stage)
    pipeline.register(JobState.PUBLISHING, publish_stage)
    return pipeline


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_worker_settings()
    ctx["sessionmaker"] = get_sessionmaker(settings.database_url)
    ctx["pipeline"] = build_pipeline()
    ctx["settings"] = settings
    ctx["stage_extra"] = {}
    logger.info("worker started")


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("worker shutting down")


async def process_job(ctx: dict[str, Any], job_id_str: str) -> str:
    """Drive a single job through the pipeline until it pauses or terminates.

    `stage_extra` is reset per job so cross-stage data (workspace path,
    findings, plans) survives within the job but doesn't leak between jobs.
    """
    sessionmaker = ctx["sessionmaker"]
    pipeline: RepairPipeline = ctx["pipeline"]
    job_id = uuid.UUID(job_id_str)
    stage_extra: dict[str, Any] = {}

    while True:
        async with sessionmaker() as session:
            new_state = await run_pipeline_step(
                pipeline,
                session=session,
                job_id=job_id,
                extra=stage_extra,
            )
        if new_state in _PAUSED_STATES or not pipeline.has_handler(new_state):
            return new_state.value


async def ingest_webhook(
    ctx: dict[str, Any],
    event_type: str,
    delivery_id: str,
    payload: dict[str, Any],
) -> str:
    """Route a GitHub webhook to the right subsystem.

    CI Guardian events go through `selfrepair.ci.dispatcher`. The original
    repo-lifecycle events (push, pull_request, installation, ...) keep
    their existing log-only behaviour until later batches wire repos.
    """
    if event_type in _CI_EVENTS:
        from selfrepair.ci.dispatcher import dispatch_ci_event

        return await dispatch_ci_event(
            ctx=ctx,
            event_type=event_type,
            delivery_id=delivery_id,
            payload=payload,
        )

    if event_type in _ISSUE_EVENTS:
        from selfrepair.issues.dispatcher import dispatch_github_issue_event

        return await dispatch_github_issue_event(
            ctx=ctx,
            event_type=event_type,
            delivery_id=delivery_id,
            payload=payload,
        )

    repo_full_name = (payload.get("repository") or {}).get("full_name")
    logger.info(
        "webhook ingested event=%s delivery=%s repo=%s",
        event_type,
        delivery_id,
        repo_full_name,
    )
    return "ingested"


async def ingest_gitlab_webhook(
    ctx: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
) -> str:
    """Route a GitLab webhook through the Issue Watch dispatcher.

    Phase-1 only handles `Issue Hook` and `Note Hook`. Anything else logs
    + returns `ignored` so adding more event types upstream doesn't crash.
    """
    from selfrepair.issues.dispatcher import dispatch_gitlab_issue_event

    return await dispatch_gitlab_issue_event(
        ctx=ctx, event_type=event_type, payload=payload
    )


from selfrepair.issues.sync import (  # noqa: E402  (kept after handlers for read order)
    scheduled_sync_external_issues,
    sync_external_issues,
)


class WorkerSettings:
    functions = [
        process_job,
        ingest_webhook,
        ingest_gitlab_webhook,
        sync_external_issues,
        scheduled_sync_external_issues,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_worker_settings().redis_url)
