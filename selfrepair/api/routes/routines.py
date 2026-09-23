"""Branch-aware Routines CRUD + protected-branch merge lock.

Phase 1 deliberately separates orchestration definitions from executors. The
console can safely model the complete repair/review/remediation/promotion chain
without introducing a second repair engine or silently enabling merges.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from selfrepair.api.deps import CtxDep, SessionDep
from selfrepair.governance.merge_guard import (
    PROTECTED_BRANCHES,
    evaluate_merge_guard,
    is_protected_branch,
)
from selfrepair.persistence.repositories.audit import AuditRepository
from selfrepair.persistence.repositories.repos import ReposRepository
from selfrepair.persistence.repositories.routines import RoutinesRepository
from selfrepair.persistence.routine_models import AutomationRoutine, RoutineRun

router = APIRouter(prefix="/v1/routines", tags=["routines"])

RoutineKind = Literal[
    "health_repair",
    "pr_review",
    "review_remediation",
    "promotion",
]
ExecutionMode = Literal["human_review", "automatic"]

_DEFAULT_REQUIREMENTS = {
    "checks_green": True,
    "reviews_resolved": True,
    "codeowners_approval": True,
}


def _serialize(row: AutomationRoutine) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "org_id": str(row.org_id),
        "repo_id": str(row.repo_id),
        "name": row.name,
        "kind": row.kind,
        "enabled": row.enabled,
        "timezone": row.timezone,
        "schedule_time": row.schedule_time,
        "schedule_days": row.schedule_days or [],
        "source_branch": row.source_branch,
        "target_branch": row.target_branch,
        "depends_on_routine_id": (
            str(row.depends_on_routine_id) if row.depends_on_routine_id else None
        ),
        "execution_mode": row.execution_mode,
        "merge_lock": row.merge_lock,
        "protected_target": is_protected_branch(row.target_branch),
        "requirements": row.requirements or {},
        "config": row.config or {},
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "created_by": str(row.created_by) if row.created_by else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _serialize_run(row: RoutineRun) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "routine_id": str(row.routine_id),
        "scheduled_for": row.scheduled_for.isoformat(),
        "status": row.status,
        "job_id": str(row.job_id) if row.job_id else None,
        "summary": row.summary,
        "details": row.details or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


class RoutineCreate(BaseModel):
    repo_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    kind: RoutineKind
    enabled: bool = True
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    schedule_time: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    schedule_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    source_branch: str = Field(..., min_length=1, max_length=255)
    target_branch: str | None = Field(default=None, max_length=255)
    depends_on_routine_id: uuid.UUID | None = None
    execution_mode: ExecutionMode = "human_review"
    requirements: dict[str, Any] = Field(default_factory=lambda: dict(_DEFAULT_REQUIREMENTS))
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schedule_days")
    @classmethod
    def validate_days(cls, value: list[int]) -> list[int]:
        days = sorted(set(value))
        if not days or any(day < 0 or day > 6 for day in days):
            raise ValueError("schedule_days must contain integers from 0 to 6")
        return days


class RoutinePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: RoutineKind | None = None
    enabled: bool | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    schedule_time: str | None = Field(
        default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    )
    schedule_days: list[int] | None = None
    source_branch: str | None = Field(default=None, min_length=1, max_length=255)
    target_branch: str | None = Field(default=None, max_length=255)
    depends_on_routine_id: uuid.UUID | None = None
    execution_mode: ExecutionMode | None = None
    requirements: dict[str, Any] | None = None
    config: dict[str, Any] | None = None

    @field_validator("schedule_days")
    @classmethod
    def validate_days(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        days = sorted(set(value))
        if not days or any(day < 0 or day > 6 for day in days):
            raise ValueError("schedule_days must contain integers from 0 to 6")
        return days


class MergeLockBody(BaseModel):
    locked: bool
    confirmation: str | None = Field(default=None, max_length=300)


class MergeGuardBody(BaseModel):
    checks_ok: bool = True
    unresolved_reviews: int = Field(default=0, ge=0)
    human_approved: bool = False


async def _validate_dependency(
    repo: RoutinesRepository,
    *,
    org_id: uuid.UUID,
    depends_on: uuid.UUID | None,
    self_id: uuid.UUID | None = None,
) -> None:
    if depends_on is None:
        return
    if self_id is not None and depends_on == self_id:
        raise HTTPException(status_code=422, detail="a routine cannot depend on itself")
    dependency = await repo.get_for_org(depends_on, org_id)
    if dependency is None:
        raise HTTPException(status_code=422, detail="dependency routine not found")


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    return {
        "available": True,
        "version": 1,
        "execution": "definition_only",
        "kinds": [
            "health_repair",
            "pr_review",
            "review_remediation",
            "promotion",
        ],
        "protected_branches": sorted(PROTECTED_BRANCHES),
        "protected_branches_locked_by_default": True,
        "automatic_merge_requires_explicit_unlock": True,
    }


@router.get("")
async def list_routines(
    ctx: CtxDep,
    session: SessionDep,
    enabled: bool | None = Query(default=None),
    repo_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    rows = await RoutinesRepository(session).list_for_org(
        org_id=ctx.org_id, enabled=enabled, repo_id=repo_id, limit=limit
    )
    return {"items": [_serialize(row) for row in rows], "count": len(rows)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_routine(
    body: RoutineCreate,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    if await ReposRepository(session).get_for_org(body.repo_id, ctx.org_id) is None:
        raise HTTPException(status_code=404, detail="repo not found")
    repo = RoutinesRepository(session)
    await _validate_dependency(
        repo, org_id=ctx.org_id, depends_on=body.depends_on_routine_id
    )
    target_branch = body.target_branch or body.source_branch
    merge_lock = is_protected_branch(target_branch)
    row = await repo.create(
        org_id=ctx.org_id,
        repo_id=body.repo_id,
        name=body.name,
        kind=body.kind,
        enabled=body.enabled,
        timezone=body.timezone,
        schedule_time=body.schedule_time,
        schedule_days=body.schedule_days,
        source_branch=body.source_branch,
        target_branch=target_branch,
        depends_on_routine_id=body.depends_on_routine_id,
        execution_mode=body.execution_mode,
        merge_lock=merge_lock,
        requirements=body.requirements,
        config=body.config,
        created_by=ctx.user_id,
    )
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="routine.create",
        target_type="routine",
        target_id=str(row.id),
        payload={
            "kind": row.kind,
            "source_branch": row.source_branch,
            "target_branch": row.target_branch,
            "merge_lock": row.merge_lock,
        },
    )
    await session.commit()
    return _serialize(row)


@router.get("/{routine_id}")
async def get_routine(
    routine_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    row = await RoutinesRepository(session).get_for_org(routine_id, ctx.org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="routine not found")
    return _serialize(row)


@router.patch("/{routine_id}")
async def patch_routine(
    routine_id: uuid.UUID,
    body: RoutinePatch,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    repo = RoutinesRepository(session)
    row = await repo.get_for_org(routine_id, ctx.org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="routine not found")
    fields = body.model_dump(exclude_unset=True)
    await _validate_dependency(
        repo,
        org_id=ctx.org_id,
        depends_on=fields.get("depends_on_routine_id"),
        self_id=routine_id,
    )
    next_target = fields.get("target_branch", row.target_branch)
    # Changing a routine to target main/master re-engages the hard lock. A
    # generic PATCH can never silently unlock a protected branch.
    if is_protected_branch(next_target) and next_target != row.target_branch:
        fields["merge_lock"] = True
    await repo.update(row, **fields)
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="routine.update",
        target_type="routine",
        target_id=str(row.id),
        payload={"fields": sorted(fields)},
    )
    await session.commit()
    return _serialize(row)


@router.delete("/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routine(
    routine_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> None:
    repo = RoutinesRepository(session)
    row = await repo.get_for_org(routine_id, ctx.org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="routine not found")
    await repo.archive(row)
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="routine.archive",
        target_type="routine",
        target_id=str(row.id),
    )
    await session.commit()


@router.post("/{routine_id}/merge-lock")
async def set_merge_lock(
    routine_id: uuid.UUID,
    body: MergeLockBody,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    repo = RoutinesRepository(session)
    row = await repo.get_for_org(routine_id, ctx.org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="routine not found")
    if not body.locked and is_protected_branch(row.target_branch):
        expected = f"UNLOCK {row.target_branch}"
        if body.confirmation != expected:
            raise HTTPException(
                status_code=409,
                detail=f'type "{expected}" to unlock automatic merges to this branch',
            )
    row.merge_lock = body.locked
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="routine.merge_lock",
        target_type="routine",
        target_id=str(row.id),
        payload={
            "locked": row.merge_lock,
            "target_branch": row.target_branch,
        },
    )
    await session.commit()
    return _serialize(row)


@router.post("/{routine_id}/merge-guard")
async def evaluate_routine_merge(
    routine_id: uuid.UUID,
    body: MergeGuardBody,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    row = await RoutinesRepository(session).get_for_org(routine_id, ctx.org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="routine not found")
    if not row.target_branch:
        raise HTTPException(status_code=422, detail="routine has no merge target")
    decision = evaluate_merge_guard(
        target_branch=row.target_branch,
        execution_mode=row.execution_mode,
        merge_lock=row.merge_lock,
        checks_ok=body.checks_ok,
        unresolved_reviews=body.unresolved_reviews,
        human_approved=body.human_approved,
    )
    return {"allowed": decision.allowed, "reason": decision.reason}


@router.get("/{routine_id}/runs")
async def list_routine_runs(
    routine_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    repo = RoutinesRepository(session)
    row = await repo.get_for_org(routine_id, ctx.org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="routine not found")
    runs = await repo.list_runs(routine_id=routine_id, org_id=ctx.org_id, limit=limit)
    return {"items": [_serialize_run(run) for run in runs], "count": len(runs)}
