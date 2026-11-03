"""Arq worker entrypoint.

Run with::

    arq selfrepair.worker.main.WorkerSettings

Registers these job functions:

- `process_job(job_id)`: drives a job through the state machine until it
  pauses or terminates.
- `ingest_webhook(event_type, delivery_id, payload)`: translates a GitHub
  webhook into job(s); CI events route through `selfrepair.ci.dispatcher`,
  push and pull_request through `selfrepair.reviewer.dispatcher`.
- `ingest_gitlab_webhook(event_type, payload, delivery_id=None)`: Merge
  Request Hooks go to the reviewer, issue hooks to Issue Watch.
- `retry_review(review_id)` and `remediate_review(review_id, task_id)`:
  enqueued by `/v1/reviews`.
- `sync_external_issues` / `scheduled_sync_external_issues`.
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
    from selfrepair.reviewer.credentials import credential_status, github_app_from_env

    ctx["github_app"] = github_app_from_env()
    logger.info("worker started reviewer_credentials=%s", credential_status())


async def shutdown(ctx: dict[str, Any]) -> None:
    app = ctx.get("github_app")
    if app is not None:
        await app.aclose()
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

    CI Guardian events go through `selfrepair.ci.dispatcher`. Push and
    pull_request events go through `selfrepair.reviewer.dispatcher`.
    Installation events stay log-only.
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

    if event_type in {"push", "pull_request"}:
        from selfrepair.reviewer.dispatcher import dispatch_github_review_event

        return await dispatch_github_review_event(
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
    delivery_id: str | None = None,
) -> str:
    """Route a GitLab webhook.

    `delivery_id` is GitLab's `X-Gitlab-Event-UUID` when the API saw one, so a
    redelivery does not start a second review. Older queued jobs omit it.

    Merge Request Hooks go to the reviewer. Issue and note hooks stay with
    Issue Watch. Anything else is ignored by that dispatcher.
    """
    if event_type == "Merge Request Hook":
        from selfrepair.reviewer.dispatcher import dispatch_gitlab_review_event

        return await dispatch_gitlab_review_event(
            ctx=ctx, event_type=event_type, payload=payload, delivery_id=delivery_id
        )

    from selfrepair.issues.dispatcher import dispatch_gitlab_issue_event

    return await dispatch_gitlab_issue_event(
        ctx=ctx, event_type=event_type, payload=payload
    )


async def retry_review(ctx: dict[str, Any], review_id: str) -> str:
    """Re-run one stored review. The API enqueues this; it does not call GitHub itself."""
    from selfrepair.reviewer.dispatcher import rerun_review

    return await rerun_review(ctx, review_id)


async def remediate_review(ctx: dict[str, Any], review_id: str, task_id: str) -> str:
    """Send one approved or dry-run remediation task to GitPilot `POST /repair`.

    The task and its plan were validated and stored by the API. This job does
    not approve, merge, or push; it records GitPilot's answer on the run.
    """
    from selfrepair.reviewer.dispatcher import store_from_ctx
    from selfrepair.reviewer.remediation import RemediationRefused, execute_task

    store = store_from_ctx(ctx)
    if store is None:
        return "tracked"
    try:
        task = await execute_task(
            store=store,
            review_id=uuid.UUID(review_id),
            task_id=task_id,
            client=ctx.get("gitpilot_client"),
        )
    except RemediationRefused as exc:
        logger.info("remediation ignored review=%s reason=%s", review_id, exc.reason)
        return "ignored"
    return str(task.get("status"))


from selfrepair.issues.sync import (  # noqa: E402  (kept after handlers for read order)
    scheduled_sync_external_issues,
    sync_external_issues,
)


class WorkerSettings:
    functions = [
        process_job,
        ingest_webhook,
        ingest_gitlab_webhook,
        retry_review,
        remediate_review,
        sync_external_issues,
        scheduled_sync_external_issues,
    ]
    on_startup = startup
    on_shutdown = shutdown
    # Reviews can run for the configured engine budget (default 600s). Arq's
    # own default of 300s would kill a live review before it can publish.
    job_timeout = get_worker_settings().job_timeout_seconds
    redis_settings = RedisSettings.from_dsn(get_worker_settings().redis_url)
