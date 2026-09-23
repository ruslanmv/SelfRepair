"""Persistence seam for SelfRepair Routines."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.routine_models import AutomationRoutine, RoutineRun


class RoutinesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_org(
        self,
        *,
        org_id: uuid.UUID,
        enabled: bool | None = None,
        repo_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[AutomationRoutine]:
        stmt = (
            select(AutomationRoutine)
            .where(
                AutomationRoutine.org_id == org_id,
                AutomationRoutine.archived_at.is_(None),
            )
            .order_by(AutomationRoutine.created_at.desc())
            .limit(limit)
        )
        if enabled is not None:
            stmt = stmt.where(AutomationRoutine.enabled == enabled)
        if repo_id is not None:
            stmt = stmt.where(AutomationRoutine.repo_id == repo_id)
        return list((await self._session.execute(stmt)).scalars())

    async def get_for_org(
        self, routine_id: uuid.UUID, org_id: uuid.UUID
    ) -> AutomationRoutine | None:
        stmt = select(AutomationRoutine).where(
            AutomationRoutine.id == routine_id,
            AutomationRoutine.org_id == org_id,
            AutomationRoutine.archived_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(self, **fields: Any) -> AutomationRoutine:
        row = AutomationRoutine(**fields)
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self, routine: AutomationRoutine, **fields: Any
    ) -> AutomationRoutine:
        for key, value in fields.items():
            if hasattr(routine, key):
                setattr(routine, key, value)
        await self._session.flush()
        return routine

    async def archive(self, routine: AutomationRoutine) -> None:
        routine.enabled = False
        routine.archived_at = datetime.now(UTC)
        await self._session.flush()

    async def list_runs(
        self,
        *,
        routine_id: uuid.UUID,
        org_id: uuid.UUID,
        limit: int = 50,
    ) -> list[RoutineRun]:
        stmt = (
            select(RoutineRun)
            .where(
                RoutineRun.routine_id == routine_id,
                RoutineRun.org_id == org_id,
            )
            .order_by(RoutineRun.created_at.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())
