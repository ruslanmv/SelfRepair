"""Repository for `repair_schedule`.

The console's Auto-repair surface manages cron-driven repair schedules;
the execution loop is the worker's `scheduled_*` arq jobs (separate
batch). This module is the CRUD seam.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.console_models import RepairSchedule


class SchedulesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_org(
        self,
        *,
        org_id: uuid.UUID,
        enabled: bool | None = None,
        limit: int = 100,
    ) -> list[RepairSchedule]:
        stmt = (
            select(RepairSchedule)
            .where(RepairSchedule.org_id == org_id)
            .order_by(RepairSchedule.created_at.desc())
            .limit(limit)
        )
        if enabled is not None:
            stmt = stmt.where(RepairSchedule.enabled == enabled)
        return list((await self._session.execute(stmt)).scalars())

    async def get_for_org(
        self, schedule_id: uuid.UUID, org_id: uuid.UUID
    ) -> RepairSchedule | None:
        stmt = select(RepairSchedule).where(
            RepairSchedule.id == schedule_id,
            RepairSchedule.org_id == org_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        org_id: uuid.UUID,
        name: str,
        cron: str,
        timezone: str = "UTC",
        repo_ids: list[str] | None = None,
        policy: str | None = None,
        trigger_label: str | None = None,
        enabled: bool = True,
        created_by: uuid.UUID | None = None,
    ) -> RepairSchedule:
        row = RepairSchedule(
            org_id=org_id,
            name=name,
            cron=cron,
            timezone=timezone,
            repo_ids=repo_ids or [],
            policy=policy,
            trigger_label=trigger_label,
            enabled=enabled,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self,
        schedule: RepairSchedule,
        **fields: Any,
    ) -> RepairSchedule:
        for k, v in fields.items():
            if hasattr(schedule, k) and v is not None:
                setattr(schedule, k, v)
        await self._session.flush()
        return schedule

    async def delete(self, schedule: RepairSchedule) -> None:
        await self._session.delete(schedule)
        await self._session.flush()
