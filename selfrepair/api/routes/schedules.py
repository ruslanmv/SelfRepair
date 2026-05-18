"""`/v1/schedules` — auto-repair schedule CRUD.

Backs `AutoRepairModal.jsx`. Cron strings are stored verbatim and
validated by the worker scheduler; the API enforces only basic shape.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from selfrepair.api.deps import CtxDep, SessionDep
from selfrepair.persistence.console_models import RepairSchedule
from selfrepair.persistence.repositories.schedules import SchedulesRepository

router = APIRouter(prefix="/v1/schedules", tags=["schedules"])


def _serialize(s: RepairSchedule) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "org_id": str(s.org_id),
        "name": s.name,
        "cron": s.cron,
        "timezone": s.timezone,
        "repo_ids": s.repo_ids or [],
        "policy": s.policy,
        "trigger_label": s.trigger_label,
        "enabled": s.enabled,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "created_by": str(s.created_by) if s.created_by else None,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }


class CreateScheduleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    cron: str = Field(..., min_length=1, max_length=64)
    timezone: str = Field(default="UTC", max_length=64)
    repo_ids: list[uuid.UUID] = Field(default_factory=list)
    policy: str | None = Field(default=None, max_length=255)
    trigger_label: str | None = Field(default=None, max_length=64)
    enabled: bool = True


class PatchScheduleRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    cron: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=64)
    repo_ids: list[uuid.UUID] | None = None
    policy: str | None = Field(default=None, max_length=255)
    trigger_label: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None


@router.get("")
async def list_schedules(
    ctx: CtxDep,
    session: SessionDep,
    enabled: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    rows = await SchedulesRepository(session).list_for_org(
        org_id=ctx.org_id, enabled=enabled, limit=limit
    )
    return {"items": [_serialize(r) for r in rows], "count": len(rows)}


@router.get("/{schedule_id}")
async def get_schedule(
    schedule_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    row = await SchedulesRepository(session).get_for_org(
        schedule_id, ctx.org_id
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found"
        )
    return _serialize(row)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: CreateScheduleRequest,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    row = await SchedulesRepository(session).create(
        org_id=ctx.org_id,
        name=body.name,
        cron=body.cron,
        timezone=body.timezone,
        repo_ids=[str(r) for r in body.repo_ids],
        policy=body.policy,
        trigger_label=body.trigger_label,
        enabled=body.enabled,
        created_by=ctx.user_id,
    )
    await session.commit()
    return _serialize(row)


@router.patch("/{schedule_id}")
async def patch_schedule(
    schedule_id: uuid.UUID,
    body: PatchScheduleRequest,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    repo = SchedulesRepository(session)
    row = await repo.get_for_org(schedule_id, ctx.org_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found"
        )
    fields = body.model_dump(exclude_none=True)
    if "repo_ids" in fields and fields["repo_ids"] is not None:
        fields["repo_ids"] = [str(r) for r in fields["repo_ids"]]
    await repo.update(row, **fields)
    await session.commit()
    return _serialize(row)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> None:
    repo = SchedulesRepository(session)
    row = await repo.get_for_org(schedule_id, ctx.org_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found"
        )
    await repo.delete(row)
    await session.commit()
