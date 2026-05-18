"""Repository for policy bundle versions and policy decisions.

Decisions are written by the worker (one row per `repair_id`) and by
the API mutation layer when an operator approves/rejects a repair.
PolicyDecision has no `org_id` of its own, so scoping joins through
Repair -> Job.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.console_models import PolicyBundleVersion
from selfrepair.persistence.models import Job, PolicyDecision, Repair


class PoliciesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_versions(
        self,
        *,
        org_id: uuid.UUID,
        limit: int = 50,
        after_created_at: datetime | None = None,
    ) -> list[PolicyBundleVersion]:
        stmt = (
            select(PolicyBundleVersion)
            .where(PolicyBundleVersion.org_id == org_id)
            .order_by(PolicyBundleVersion.created_at.desc())
            .limit(limit)
        )
        if after_created_at is not None:
            stmt = stmt.where(PolicyBundleVersion.created_at < after_created_at)
        return list((await self._session.execute(stmt)).scalars())

    async def get_version(
        self, version_id: uuid.UUID, org_id: uuid.UUID
    ) -> PolicyBundleVersion | None:
        stmt = select(PolicyBundleVersion).where(
            PolicyBundleVersion.id == version_id,
            PolicyBundleVersion.org_id == org_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_version(
        self,
        *,
        org_id: uuid.UUID,
        version: str,
        bundle_sha: str,
        bundle_object_url: str,
        description: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> PolicyBundleVersion:
        row = PolicyBundleVersion(
            org_id=org_id,
            version=version,
            bundle_sha=bundle_sha,
            bundle_object_url=bundle_object_url,
            description=description,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_decisions(
        self,
        *,
        org_id: uuid.UUID,
        repair_id: uuid.UUID | None = None,
        outcome: str | None = None,
        limit: int = 100,
        after_id: uuid.UUID | None = None,
    ) -> list[PolicyDecision]:
        stmt = (
            select(PolicyDecision)
            .join(Repair, Repair.id == PolicyDecision.repair_id)
            .join(Job, Job.id == Repair.job_id)
            .where(Job.org_id == org_id)
            .order_by(PolicyDecision.id.desc())
            .limit(limit)
        )
        if repair_id is not None:
            stmt = stmt.where(PolicyDecision.repair_id == repair_id)
        if outcome is not None:
            stmt = stmt.where(PolicyDecision.outcome == outcome)
        if after_id is not None:
            stmt = stmt.where(PolicyDecision.id < after_id)
        return list((await self._session.execute(stmt)).scalars())

    async def record_decision(
        self,
        *,
        repair_id: uuid.UUID,
        rule_id: str,
        outcome: str,
        requires_approval: bool = False,
        approver_id: uuid.UUID | None = None,
    ) -> PolicyDecision:
        row = PolicyDecision(
            repair_id=repair_id,
            rule_id=rule_id,
            outcome=outcome,
            requires_approval=requires_approval,
            approver_id=approver_id,
            decided_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row
