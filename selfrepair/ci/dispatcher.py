"""CI event dispatcher.

Phase 1 responsibilities:
  * de-dupe webhooks by delivery_id (Redis fast-path; the DB unique
    constraint on (repo_id, github_run_id, run_attempt) is the source of
    truth)
  * validate the payload via the Pydantic schemas in selfrepair.ci.schemas
  * persist workflow_run / workflow_job rows via `CIRepository` when a
    sessionmaker is wired into ctx; otherwise log-only (test/local mode)

The function signature matches what `worker.main.ingest_webhook` calls.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from selfrepair.ci.config import CIGuardianRuntime, get_runtime
from selfrepair.ci.schemas import WorkflowJobEvent, WorkflowRunEvent
from selfrepair.persistence.models import Repo
from selfrepair.persistence.repositories import CIRepository

logger = logging.getLogger(__name__)


async def dispatch_ci_event(
    *,
    ctx: dict[str, Any],
    event_type: str,
    delivery_id: str,
    payload: dict[str, Any],
) -> str:
    """Route a CI event to the right handler.

    Returns one of:
        "ignored"      — kill switch or unknown event
        "duplicate"    — same delivery_id processed already
        "tracked"      — event accepted (persistence wired in batch 3)
    """
    runtime = get_runtime()
    if runtime.kill_switch:
        logger.info("ci dispatcher: kill switch is on; dropping %s", event_type)
        return "ignored"

    if not await _claim_delivery(ctx, delivery_id, runtime):
        logger.info("ci dispatcher: duplicate delivery %s", delivery_id)
        return "duplicate"

    repo_full_name = (payload.get("repository") or {}).get("full_name")
    if not repo_full_name:
        logger.info("ci dispatcher: payload missing repository.full_name")
        return "ignored"

    if event_type == "workflow_run":
        try:
            event = WorkflowRunEvent.model_validate(payload)
        except Exception:
            logger.exception("ci dispatcher: invalid workflow_run payload")
            return "ignored"
        return await _handle_workflow_run(ctx, event, delivery_id)

    if event_type == "workflow_job":
        try:
            event = WorkflowJobEvent.model_validate(payload)
        except Exception:
            logger.exception("ci dispatcher: invalid workflow_job payload")
            return "ignored"
        return await _handle_workflow_job(ctx, event, delivery_id)

    # check_run / check_suite — acknowledged in Phase 1; full handling
    # arrives with the Checks API integration in Phase 5.
    logger.info(
        "ci dispatcher: noting %s event but not yet handled (delivery=%s)",
        event_type,
        delivery_id,
    )
    return "tracked"


async def _claim_delivery(
    ctx: dict[str, Any],
    delivery_id: str,
    runtime: CIGuardianRuntime,
) -> bool:
    """Redis SET-NX fast-path for delivery dedupe.

    The DB unique constraint on (repo_id, github_run_id, run_attempt) is
    the source of truth; this lock just avoids the upsert when GitHub
    redelivers the exact same event.
    """
    if not delivery_id:
        return True
    redis = ctx.get("redis")
    if redis is None:
        # No Redis configured (unit tests, local-only setups); skip the
        # cheap check. The DB constraint still catches the duplicate.
        return True
    key = f"selfrepair:ci:delivery:{delivery_id}"
    try:
        result = await redis.set(
            key, "1", ex=runtime.redis_dedupe_ttl_seconds, nx=True
        )
    except Exception:
        logger.warning(
            "ci dispatcher: redis claim failed; continuing", exc_info=True
        )
        return True
    return result is not None


async def _handle_workflow_run(
    ctx: dict[str, Any],
    event: WorkflowRunEvent,
    delivery_id: str,
) -> str:
    logger.info(
        "ci.workflow_run action=%s repo=%s run_id=%s attempt=%s status=%s conclusion=%s delivery=%s",
        event.action,
        event.repository.full_name,
        event.workflow_run.id,
        event.workflow_run.run_attempt,
        event.workflow_run.status,
        event.workflow_run.conclusion,
        delivery_id,
    )
    sessionmaker = ctx.get("sessionmaker")
    if sessionmaker is None:
        return "tracked"
    async with sessionmaker() as session:
        repo = await _resolve_repo(session, event.repository.full_name)
        if repo is None:
            logger.info(
                "ci dispatcher: unknown repo %s; storing nothing",
                event.repository.full_name,
            )
            return "ignored"
        run = event.workflow_run
        ci_repo = CIRepository(session)
        await ci_repo.upsert_workflow_run(
            org_id=repo.org_id,
            repo_id=repo.id,
            github_run_id=run.id,
            run_attempt=run.run_attempt,
            github_workflow_id=run.workflow_id,
            workflow_name=run.name,
            workflow_path=run.path,
            head_sha=run.head_sha,
            head_branch=run.head_branch,
            event=run.event,
            status=run.status,
            conclusion=run.conclusion,
            html_url=run.html_url,
            started_at=run.run_started_at,
            completed_at=run.updated_at if run.status == "completed" else None,
            last_event=event.action,
            delivery_id=delivery_id,
            raw=event.model_dump(mode="json"),
        )
        await session.commit()
    return "tracked"


async def _handle_workflow_job(
    ctx: dict[str, Any],
    event: WorkflowJobEvent,
    delivery_id: str,
) -> str:
    logger.info(
        "ci.workflow_job action=%s repo=%s job_id=%s run_id=%s status=%s conclusion=%s delivery=%s",
        event.action,
        event.repository.full_name,
        event.workflow_job.id,
        event.workflow_job.run_id,
        event.workflow_job.status,
        event.workflow_job.conclusion,
        delivery_id,
    )
    sessionmaker = ctx.get("sessionmaker")
    if sessionmaker is None:
        return "tracked"
    async with sessionmaker() as session:
        repo = await _resolve_repo(session, event.repository.full_name)
        if repo is None:
            return "ignored"
        ci_repo = CIRepository(session)
        run_row = await ci_repo.get_workflow_run_by_github_id(
            repo_id=repo.id,
            github_run_id=event.workflow_job.run_id,
            run_attempt=None,
        )
        if run_row is None:
            # Job webhook beat the run webhook; create a minimal placeholder
            # so the job FK has a target. The run upsert later fills it in.
            run_row = await ci_repo.upsert_workflow_run(
                org_id=repo.org_id,
                repo_id=repo.id,
                github_run_id=event.workflow_job.run_id,
                run_attempt=None,
                last_event=f"job:{event.action}",
                delivery_id=delivery_id,
            )
        job = event.workflow_job
        failed_step_name, step_failure_index = _find_failed_step(job)
        await ci_repo.upsert_workflow_job(
            workflow_run_id=run_row.id,
            github_job_id=job.id,
            name=job.name,
            status=job.status,
            conclusion=job.conclusion,
            runner_name=job.runner_name,
            started_at=job.started_at,
            completed_at=job.completed_at,
            failed_step_name=failed_step_name,
            step_failure_index=step_failure_index,
            raw=event.model_dump(mode="json"),
        )
        await session.commit()
    return "tracked"


async def _resolve_repo(session: Any, full_name: str) -> Repo | None:
    stmt = select(Repo).where(
        Repo.provider == "github", Repo.full_name == full_name
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _find_failed_step(job: Any) -> tuple[str | None, int | None]:
    """Return (name, index) of the first failed step, or (None, None)."""
    for step in job.steps or []:
        if step.conclusion == "failure":
            return step.name, step.number
    return None, None
