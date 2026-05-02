"""Repository for CI Guardian rows: workflow_run, workflow_job, ci_failure.

Three load-bearing methods:

  * `upsert_workflow_run` — idempotent on (repo_id, github_run_id, run_attempt).
    GitHub redelivers the same run as it transitions through `requested`,
    `in_progress`, `completed`; the unique constraint folds them together.

  * `upsert_workflow_job` — idempotent on (workflow_run_id, github_job_id).

  * `record_failure` — `ci_failure` is the dedup table. Same flake across
    many runs collapses to one row with a growing `occurrence_count`. The
    dispatcher computes the fingerprint with selfrepair.ci.fingerprints; this
    repo just inserts-or-bumps it.

The dispatcher passes the original webhook payload as `raw`. We never strip
fields from it — additive forward compatibility.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import (
    CIFailure,
    CIFailureStatus,
    CIWorkflowJob,
    CIWorkflowRun,
)


class CIRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---------------- workflow_run ----------------

    async def upsert_workflow_run(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        github_run_id: int,
        run_attempt: int | None,
        github_workflow_id: int | None = None,
        workflow_name: str | None = None,
        workflow_path: str | None = None,
        head_sha: str | None = None,
        head_branch: str | None = None,
        event: str | None = None,
        status: str | None = None,
        conclusion: str | None = None,
        html_url: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        last_event: str | None = None,
        delivery_id: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> CIWorkflowRun:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(CIWorkflowRun)
            .values(
                org_id=org_id,
                repo_id=repo_id,
                github_run_id=github_run_id,
                run_attempt=run_attempt,
                github_workflow_id=github_workflow_id,
                workflow_name=workflow_name,
                workflow_path=workflow_path,
                head_sha=head_sha,
                head_branch=head_branch,
                event=event,
                status=status,
                conclusion=conclusion,
                html_url=html_url,
                started_at=started_at,
                completed_at=completed_at,
                last_synced_at=now,
                last_event=last_event,
                delivery_id=delivery_id,
                raw=raw,
            )
            .on_conflict_do_update(
                constraint="uq_ci_run_attempt",
                set_={
                    "status": status,
                    "conclusion": conclusion,
                    "completed_at": completed_at,
                    "last_synced_at": now,
                    "last_event": last_event,
                    "delivery_id": delivery_id,
                    "raw": raw,
                },
            )
            .returning(CIWorkflowRun)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def get_workflow_run(
        self, run_id: uuid.UUID
    ) -> CIWorkflowRun | None:
        return await self._session.get(CIWorkflowRun, run_id)

    async def get_workflow_run_by_github_id(
        self,
        *,
        repo_id: uuid.UUID,
        github_run_id: int,
        run_attempt: int | None,
    ) -> CIWorkflowRun | None:
        stmt = select(CIWorkflowRun).where(
            CIWorkflowRun.repo_id == repo_id,
            CIWorkflowRun.github_run_id == github_run_id,
            CIWorkflowRun.run_attempt == run_attempt,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # ---------------- workflow_job ----------------

    async def upsert_workflow_job(
        self,
        *,
        workflow_run_id: uuid.UUID,
        github_job_id: int,
        name: str | None = None,
        status: str | None = None,
        conclusion: str | None = None,
        runner_name: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        failed_step_name: str | None = None,
        step_failure_index: int | None = None,
        log_excerpt: str | None = None,
        log_object_key: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> CIWorkflowJob:
        stmt = (
            pg_insert(CIWorkflowJob)
            .values(
                workflow_run_id=workflow_run_id,
                github_job_id=github_job_id,
                name=name,
                status=status,
                conclusion=conclusion,
                runner_name=runner_name,
                started_at=started_at,
                completed_at=completed_at,
                failed_step_name=failed_step_name,
                step_failure_index=step_failure_index,
                log_excerpt=log_excerpt,
                log_object_key=log_object_key,
                raw=raw,
            )
            .on_conflict_do_update(
                constraint="uq_ci_workflow_job",
                set_={
                    "status": status,
                    "conclusion": conclusion,
                    "completed_at": completed_at,
                    "failed_step_name": failed_step_name,
                    "step_failure_index": step_failure_index,
                    "log_excerpt": log_excerpt,
                    "log_object_key": log_object_key,
                    "raw": raw,
                },
            )
            .returning(CIWorkflowJob)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def list_jobs_for_run(
        self, workflow_run_id: uuid.UUID
    ) -> list[CIWorkflowJob]:
        stmt = (
            select(CIWorkflowJob)
            .where(CIWorkflowJob.workflow_run_id == workflow_run_id)
            .order_by(CIWorkflowJob.started_at)
        )
        return list((await self._session.execute(stmt)).scalars())

    # ---------------- ci_failure ----------------

    async def record_failure(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        workflow_run_id: uuid.UUID,
        workflow_job_id: uuid.UUID | None,
        fingerprint: str,
        failure_class: str,
        severity: str,
        confidence: float | None = None,
        last_error_signature: str | None = None,
        policy_decision: dict[str, Any] | None = None,
        kill_switched: bool = False,
        redacted_secret_count: int = 0,
        diagnostic: dict[str, Any] | None = None,
    ) -> CIFailure:
        """Insert-or-bump a deduplicated failure row.

        On first occurrence: insert with `occurrence_count=1`. On subsequent
        occurrences: bump `occurrence_count`, refresh `last_seen_at`, and
        update the latest workflow_run/job pointers + last error signature.
        Status is preserved on update so an in-flight repair isn't reset.
        """
        now = datetime.now(UTC)
        stmt = (
            pg_insert(CIFailure)
            .values(
                org_id=org_id,
                repo_id=repo_id,
                workflow_run_id=workflow_run_id,
                workflow_job_id=workflow_job_id,
                fingerprint=fingerprint,
                failure_class=failure_class,
                severity=severity,
                status=CIFailureStatus.OPEN,
                confidence=confidence,
                first_seen_at=now,
                last_seen_at=now,
                occurrence_count=1,
                last_error_signature=last_error_signature,
                policy_decision=policy_decision,
                kill_switched=kill_switched,
                redacted_secret_count=redacted_secret_count,
                diagnostic=diagnostic,
            )
            .on_conflict_do_update(
                constraint="uq_ci_failure_fingerprint",
                set_={
                    "workflow_run_id": workflow_run_id,
                    "workflow_job_id": workflow_job_id,
                    "last_seen_at": now,
                    "occurrence_count": CIFailure.__table__.c.occurrence_count + 1,
                    "last_error_signature": last_error_signature,
                    "policy_decision": policy_decision,
                    "kill_switched": kill_switched,
                    "redacted_secret_count": redacted_secret_count,
                    "diagnostic": diagnostic,
                    "severity": severity,
                    "failure_class": failure_class,
                },
            )
            .returning(CIFailure)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def get_failure(
        self, failure_id: uuid.UUID
    ) -> CIFailure | None:
        return await self._session.get(CIFailure, failure_id)

    async def list_failures_for_repo(
        self,
        repo_id: uuid.UUID,
        *,
        statuses: tuple[CIFailureStatus, ...] | None = None,
        limit: int = 100,
    ) -> list[CIFailure]:
        stmt = select(CIFailure).where(CIFailure.repo_id == repo_id)
        if statuses:
            stmt = stmt.where(CIFailure.status.in_(statuses))
        stmt = stmt.order_by(CIFailure.last_seen_at.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars())

    async def list_open_failures_for_org(
        self, org_id: uuid.UUID, *, limit: int = 100
    ) -> list[CIFailure]:
        stmt = (
            select(CIFailure)
            .where(
                CIFailure.org_id == org_id,
                CIFailure.status == CIFailureStatus.OPEN,
            )
            .order_by(CIFailure.last_seen_at.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def transition_failure(
        self,
        failure_id: uuid.UUID,
        target: CIFailureStatus,
        *,
        repair_job_id: uuid.UUID | None = None,
        repair_pr_url: str | None = None,
        auto_action: str | None = None,
    ) -> CIFailure:
        """Apply a status transition. The state machine is enforced by the
        caller — this method just updates the row, sets `resolved_at` for
        terminal states, and threads optional repair-job linkage."""
        failure = await self.get_failure(failure_id)
        if failure is None:
            raise LookupError(f"ci_failure {failure_id} not found")
        failure.status = target
        if target in _TERMINAL_STATES:
            failure.resolved_at = datetime.now(UTC)
        if repair_job_id is not None:
            failure.repair_job_id = repair_job_id
        if repair_pr_url is not None:
            failure.repair_pr_url = repair_pr_url
        if auto_action is not None:
            failure.auto_action = auto_action
        return failure


_TERMINAL_STATES: frozenset[CIFailureStatus] = frozenset(
    {
        CIFailureStatus.RESOLVED,
        CIFailureStatus.SUPPRESSED,
        CIFailureStatus.ESCALATED,
    }
)
