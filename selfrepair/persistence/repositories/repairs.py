"""Repository for repair attempts."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import Repair, RepairMode, RepairState


class RepairsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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

    async def get(self, repair_id: uuid.UUID) -> Repair | None:
        return await self._session.get(Repair, repair_id)

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

    async def latest_for_finding(self, finding_id: uuid.UUID) -> Repair | None:
        stmt = (
            select(Repair)
            .where(Repair.finding_id == finding_id)
            .order_by(Repair.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
