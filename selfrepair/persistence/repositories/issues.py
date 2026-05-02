"""Repository for Issue Watch — external_issue + external_issue_action.

Two load-bearing methods:

  * `upsert_issue` — idempotent on (org_id, provider, provider_issue_id).
    The provider sync polls every minute or so; we want the same external
    issue to collapse to a single row with refreshed state, labels, and
    last_synced_at. Title/body/state can change upstream; the upsert
    overwrites them.

  * `record_action` — one row per mutating action (sync, run_repair,
    triage, comment, suppress, …). This is the audit trail back to the
    pipeline: a `run_repair` action carries a job_id forward link.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import (
    ExternalIssue,
    ExternalIssueAction,
    ExternalIssueActionType,
)


class IssuesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---------------- external_issue ----------------

    async def upsert_issue(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        provider: str,
        provider_issue_id: str,
        number: int,
        title: str,
        fingerprint: str,
        body_excerpt: str | None = None,
        state: str = "open",
        author: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
        priority: str | None = None,
        repair_class: str | None = None,
        repairable: bool = False,
        html_url: str | None = None,
        created_at_external: datetime | None = None,
        updated_at_external: datetime | None = None,
        closed_at_external: datetime | None = None,
        raw: dict[str, Any] | None = None,
    ) -> ExternalIssue:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(ExternalIssue)
            .values(
                org_id=org_id,
                repo_id=repo_id,
                provider=provider,
                provider_issue_id=provider_issue_id,
                number=number,
                title=title,
                body_excerpt=body_excerpt,
                state=state,
                author=author,
                labels=labels or [],
                assignees=assignees or [],
                priority=priority,
                repair_class=repair_class,
                repairable=repairable,
                html_url=html_url,
                created_at_external=created_at_external,
                updated_at_external=updated_at_external,
                closed_at_external=closed_at_external,
                last_synced_at=now,
                fingerprint=fingerprint,
                raw=raw,
            )
            .on_conflict_do_update(
                constraint="uq_external_issue_provider_id",
                set_={
                    "title": title,
                    "body_excerpt": body_excerpt,
                    "state": state,
                    "labels": labels or [],
                    "assignees": assignees or [],
                    "priority": priority,
                    "repair_class": repair_class,
                    "repairable": repairable,
                    "updated_at_external": updated_at_external,
                    "closed_at_external": closed_at_external,
                    "last_synced_at": now,
                    "raw": raw,
                },
            )
            .returning(ExternalIssue)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def get_issue(self, issue_id: uuid.UUID) -> ExternalIssue | None:
        return await self._session.get(ExternalIssue, issue_id)

    async def list_issues(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None = None,
        provider: str | None = None,
        state: str | None = None,
        priority: str | None = None,
        repairable: bool | None = None,
        limit: int = 100,
    ) -> list[ExternalIssue]:
        """Filtered listing for the Open Issues surface and `/v1/issues`.

        Sorted by `updated_at_external` desc with a fallback to insertion
        order so issues without an external timestamp still appear.
        """
        stmt = select(ExternalIssue).where(ExternalIssue.org_id == org_id)
        if repo_id is not None:
            stmt = stmt.where(ExternalIssue.repo_id == repo_id)
        if provider is not None:
            stmt = stmt.where(ExternalIssue.provider == provider)
        if state is not None:
            stmt = stmt.where(ExternalIssue.state == state)
        if priority is not None:
            stmt = stmt.where(ExternalIssue.priority == priority)
        if repairable is not None:
            stmt = stmt.where(ExternalIssue.repairable == repairable)
        stmt = stmt.order_by(
            ExternalIssue.updated_at_external.desc().nulls_last(),
            ExternalIssue.last_synced_at.desc(),
        ).limit(limit)
        return list((await self._session.execute(stmt)).scalars())

    async def mark_closed(
        self, issue_id: uuid.UUID, *, closed_at: datetime | None = None
    ) -> None:
        """Used by the sync sweep to reconcile issues that are no longer
        present in the provider's open-issues list. We only flip state +
        closed_at_external; nothing else is touched."""
        issue = await self.get_issue(issue_id)
        if issue is None:
            raise LookupError(f"external_issue {issue_id} not found")
        issue.state = "closed"
        issue.closed_at_external = closed_at or datetime.now(UTC)

    # ---------------- external_issue_action ----------------

    async def record_action(
        self,
        *,
        org_id: uuid.UUID,
        external_issue_id: uuid.UUID,
        action_type: ExternalIssueActionType,
        actor: str | None = None,
        action_status: str = "pending",
        job_id: uuid.UUID | None = None,
        finding_id: uuid.UUID | None = None,
        repair_id: uuid.UUID | None = None,
        comment_url: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ExternalIssueAction:
        action = ExternalIssueAction(
            org_id=org_id,
            external_issue_id=external_issue_id,
            action_type=action_type,
            action_status=action_status,
            actor=actor,
            job_id=job_id,
            finding_id=finding_id,
            repair_id=repair_id,
            comment_url=comment_url,
            payload=payload,
        )
        self._session.add(action)
        await self._session.flush()
        return action

    async def list_actions_for_issue(
        self, external_issue_id: uuid.UUID
    ) -> list[ExternalIssueAction]:
        stmt = (
            select(ExternalIssueAction)
            .where(ExternalIssueAction.external_issue_id == external_issue_id)
            .order_by(ExternalIssueAction.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars())
