"""Repository for repair attempts.

The `repair` table itself doesn't carry `org_id` (a repair is bound to a
finding, which carries it); every read therefore joins via `finding` to
enforce tenant scope. The console list endpoint also folds in `job` and
`repo` so each row already has the names the table renders, which keeps
the N+1 trap closed.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import (
    Finding,
    Job,
    PolicyDecision,
    Provenance,
    Repair,
    RepairMode,
    RepairState,
    Repo,
)


@dataclass(frozen=True)
class RepairWithJoins:
    repair: Repair
    finding: Finding
    job: Job
    repo: Repo


@dataclass(frozen=True)
class RepairDetail:
    repair: Repair
    finding: Finding
    job: Job
    repo: Repo
    policy_decisions: list[PolicyDecision]
    provenance: Provenance | None


class RepairsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --------------------------- writes (worker) ---------------------------

    async def create(
        self,
        *,
        finding_id: uuid.UUID,
        job_id: uuid.UUID,
        fixer_id: str,
        mode: RepairMode,
        model_id: str | None = None,
        prompt_hash: str | None = None,
    ) -> Repair:
        repair = Repair(
            finding_id=finding_id,
            job_id=job_id,
            fixer_id=fixer_id,
            mode=mode,
            model_id=model_id,
            prompt_hash=prompt_hash,
        )
        self._session.add(repair)
        await self._session.flush()
        return repair

    async def update_state(
        self,
        repair_id: uuid.UUID,
        state: RepairState,
        **fields: Any,
    ) -> Repair:
        repair = await self.get(repair_id)
        if repair is None:
            raise LookupError(f"repair {repair_id} not found")
        repair.state = state
        for key, value in fields.items():
            if hasattr(repair, key):
                setattr(repair, key, value)
        return repair

    # --------------------------- reads (api) -------------------------------

    async def get(self, repair_id: uuid.UUID) -> Repair | None:
        return await self._session.get(Repair, repair_id)

    async def latest_for_finding(self, finding_id: uuid.UUID) -> Repair | None:
        stmt = (
            select(Repair)
            .where(Repair.finding_id == finding_id)
            .order_by(Repair.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_with_joins(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None = None,
        state: RepairState | None = None,
        limit: int = 50,
        after_created_at: datetime | None = None,
        after_id: uuid.UUID | None = None,
    ) -> list[RepairWithJoins]:
        stmt = (
            select(Repair, Finding, Job, Repo)
            .join(Finding, Finding.id == Repair.finding_id)
            .join(Job, Job.id == Repair.job_id)
            .join(Repo, Repo.id == Job.repo_id)
            .where(Finding.org_id == org_id, Job.org_id == org_id)
            .order_by(Repair.created_at.desc(), Repair.id.desc())
            .limit(limit)
        )
        if repo_id is not None:
            stmt = stmt.where(Job.repo_id == repo_id)
        if state is not None:
            stmt = stmt.where(Repair.state == state)
        if after_created_at is not None and after_id is not None:
            stmt = stmt.where(
                or_(
                    Repair.created_at < after_created_at,
                    and_(
                        Repair.created_at == after_created_at,
                        Repair.id < after_id,
                    ),
                )
            )
        rows = (await self._session.execute(stmt)).all()
        return [
            RepairWithJoins(repair=r, finding=f, job=j, repo=rp)
            for (r, f, j, rp) in rows
        ]

    async def detail_for_org(
        self, repair_id: uuid.UUID, org_id: uuid.UUID
    ) -> RepairDetail | None:
        stmt = (
            select(Repair, Finding, Job, Repo)
            .join(Finding, Finding.id == Repair.finding_id)
            .join(Job, Job.id == Repair.job_id)
            .join(Repo, Repo.id == Job.repo_id)
            .where(
                Repair.id == repair_id,
                Finding.org_id == org_id,
                Job.org_id == org_id,
            )
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        repair, finding, job, repo = row

        decisions = list(
            (
                await self._session.execute(
                    select(PolicyDecision)
                    .where(PolicyDecision.repair_id == repair.id)
                    .order_by(PolicyDecision.id)
                )
            ).scalars()
        )
        prov = (
            await self._session.execute(
                select(Provenance).where(Provenance.repair_id == repair.id)
            )
        ).scalar_one_or_none()
        return RepairDetail(
            repair=repair,
            finding=finding,
            job=job,
            repo=repo,
            policy_decisions=decisions,
            provenance=prov,
        )

    async def policy_decisions(
        self, repair_id: uuid.UUID
    ) -> list[PolicyDecision]:
        stmt = (
            select(PolicyDecision)
            .where(PolicyDecision.repair_id == repair_id)
            .order_by(PolicyDecision.id)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def provenance_for(
        self, repair_id: uuid.UUID
    ) -> Provenance | None:
        stmt = select(Provenance).where(Provenance.repair_id == repair_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()
