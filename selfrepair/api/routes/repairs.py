"""`/v1/repairs` — list, detail, policy/provenance, plus mutation endpoints.

Approve/reject record a policy_decision row + audit log + state
transition. Rerun-validation and publish-pr enqueue the worker; the
API never talks to providers directly.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from selfrepair.api.deps import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CtxDep,
    SessionDep,
    decode_cursor,
    encode_cursor,
)
from selfrepair.persistence.models import (
    Finding,
    Job,
    PolicyDecision,
    Provenance,
    Repair,
    RepairState,
    Repo,
)
from selfrepair.persistence.repositories.audit import AuditRepository
from selfrepair.persistence.repositories.policies import PoliciesRepository
from selfrepair.persistence.repositories.repairs import (
    RepairsRepository,
    RepairWithJoins,
)

router = APIRouter(prefix="/v1/repairs", tags=["repairs"])


def _serialize_repair(r: Repair) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "finding_id": str(r.finding_id),
        "job_id": str(r.job_id),
        "fixer_id": r.fixer_id,
        "mode": r.mode.value if hasattr(r.mode, "value") else r.mode,
        "model_id": r.model_id,
        "prompt_hash": r.prompt_hash,
        "diff_sha": r.diff_sha,
        "signed_commit_sha": r.signed_commit_sha,
        "pr_url": r.pr_url,
        "state": r.state.value if hasattr(r.state, "value") else r.state,
        "created_at": r.created_at.isoformat(),
        "cost_usd": float(r.cost_usd) if r.cost_usd is not None else 0.0,
    }


def _serialize_finding_lite(f: Finding) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "kind": f.kind,
        "severity": f.severity,
        "fingerprint": f.fingerprint,
    }


def _serialize_job_lite(j: Job) -> dict[str, Any]:
    return {
        "id": str(j.id),
        "state": j.state.value if hasattr(j.state, "value") else j.state,
        "trigger": (
            j.trigger.value if hasattr(j.trigger, "value") else j.trigger
        ),
        "started_at": j.started_at.isoformat(),
    }


def _serialize_repo_lite(r: Repo) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "provider": r.provider,
        "full_name": r.full_name,
        "default_branch": r.default_branch,
    }


def _serialize_with_joins(item: RepairWithJoins) -> dict[str, Any]:
    base = _serialize_repair(item.repair)
    base["finding"] = _serialize_finding_lite(item.finding)
    base["job"] = _serialize_job_lite(item.job)
    base["repo"] = _serialize_repo_lite(item.repo)
    return base


def _serialize_policy(d: PolicyDecision) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "repair_id": str(d.repair_id),
        "rule_id": d.rule_id,
        "outcome": d.outcome,
        "requires_approval": d.requires_approval,
        "approver_id": str(d.approver_id) if d.approver_id else None,
        "decided_at": d.decided_at.isoformat() if d.decided_at else None,
    }


def _serialize_provenance(p: Provenance) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "repair_id": str(p.repair_id),
        "builder": p.builder,
        "materials": p.materials,
        "has_attestation": p.attestation_blob is not None,
        "attestation_size": (
            len(p.attestation_blob) if p.attestation_blob else 0
        ),
        "created_at": p.created_at.isoformat(),
    }


@router.get("")
async def list_repairs(
    ctx: CtxDep,
    session: SessionDep,
    repo_id: uuid.UUID | None = Query(default=None),
    state: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    after_created_at: datetime | None = None
    after_id: uuid.UUID | None = None
    if cursor:
        c = decode_cursor(cursor)
        try:
            if c.get("after_created_at"):
                after_created_at = datetime.fromisoformat(c["after_created_at"])
            if c.get("after_id"):
                after_id = uuid.UUID(c["after_id"])
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="invalid cursor"
            ) from exc
    parsed_state: RepairState | None = None
    if state:
        try:
            parsed_state = RepairState(state)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid state: {state}"
            ) from exc

    repo = RepairsRepository(session)
    rows = await repo.list_with_joins(
        org_id=ctx.org_id,
        repo_id=repo_id,
        state=parsed_state,
        limit=limit + 1,
        after_created_at=after_created_at,
        after_id=after_id,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor(
            {
                "after_created_at": page[-1].repair.created_at.isoformat(),
                "after_id": str(page[-1].repair.id),
            }
        )
        if has_more and page
        else None
    )
    return {
        "items": [_serialize_with_joins(r) for r in page],
        "count": len(page),
        "next_cursor": next_cursor,
    }


@router.get("/{repair_id}")
async def get_repair(
    repair_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    detail = await RepairsRepository(session).detail_for_org(
        repair_id, ctx.org_id
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repair not found"
        )
    return {
        **_serialize_repair(detail.repair),
        "finding": _serialize_finding_lite(detail.finding),
        "job": _serialize_job_lite(detail.job),
        "repo": _serialize_repo_lite(detail.repo),
        "policy_decisions": [
            _serialize_policy(d) for d in detail.policy_decisions
        ],
        "provenance": (
            _serialize_provenance(detail.provenance)
            if detail.provenance
            else None
        ),
    }


@router.get("/{repair_id}/diff")
async def get_repair_diff(
    repair_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    detail = await RepairsRepository(session).detail_for_org(
        repair_id, ctx.org_id
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repair not found"
        )
    return {
        "repair_id": str(detail.repair.id),
        "diff_sha": detail.repair.diff_sha,
        "diff": None,
        "sandbox_result": detail.repair.sandbox_result,
    }


@router.get("/{repair_id}/policy")
async def get_repair_policy(
    repair_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    detail = await RepairsRepository(session).detail_for_org(
        repair_id, ctx.org_id
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repair not found"
        )
    return {
        "repair_id": str(detail.repair.id),
        "decisions": [_serialize_policy(d) for d in detail.policy_decisions],
    }


@router.get("/{repair_id}/provenance")
async def get_repair_provenance(
    repair_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    detail = await RepairsRepository(session).detail_for_org(
        repair_id, ctx.org_id
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repair not found"
        )
    return {
        "repair_id": str(detail.repair.id),
        "provenance": (
            _serialize_provenance(detail.provenance)
            if detail.provenance
            else None
        ),
    }


# ----------------------------- mutations -----------------------------


class DecisionBody(BaseModel):
    rule_id: str = Field(default="manual.review", max_length=255)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/{repair_id}/approve")
async def approve_repair(
    repair_id: uuid.UUID,
    body: DecisionBody,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    detail = await RepairsRepository(session).detail_for_org(
        repair_id, ctx.org_id
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repair not found"
        )
    decision = await PoliciesRepository(session).record_decision(
        repair_id=repair_id,
        rule_id=body.rule_id,
        outcome="allow",
        requires_approval=True,
        approver_id=ctx.user_id,
    )
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="repair.approve",
        target_type="repair",
        target_id=str(repair_id),
        payload={"note": body.note} if body.note else None,
    )
    await session.commit()
    return {
        "repair_id": str(repair_id),
        "decision": _serialize_policy(decision),
    }


@router.post("/{repair_id}/reject")
async def reject_repair(
    repair_id: uuid.UUID,
    body: DecisionBody,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    repo = RepairsRepository(session)
    detail = await repo.detail_for_org(repair_id, ctx.org_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repair not found"
        )
    decision = await PoliciesRepository(session).record_decision(
        repair_id=repair_id,
        rule_id=body.rule_id,
        outcome="deny",
        requires_approval=True,
        approver_id=ctx.user_id,
    )
    await repo.update_state(repair_id, RepairState.FAILED)
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="repair.reject",
        target_type="repair",
        target_id=str(repair_id),
        payload={"note": body.note} if body.note else None,
    )
    await session.commit()
    return {
        "repair_id": str(repair_id),
        "decision": _serialize_policy(decision),
        "state": RepairState.FAILED.value,
    }


@router.post(
    "/{repair_id}/rerun-validation", status_code=status.HTTP_202_ACCEPTED
)
async def rerun_validation(
    repair_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
    request: Request,
) -> dict[str, Any]:
    detail = await RepairsRepository(session).detail_for_org(
        repair_id, ctx.org_id
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repair not found"
        )
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="repair.rerun_validation",
        target_type="repair",
        target_id=str(repair_id),
    )
    await session.commit()
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        try:
            await queue.enqueue_job(
                "rerun_validation", str(repair_id)
            )
        except Exception:
            pass
    return {"repair_id": str(repair_id), "status": "queued"}


@router.post(
    "/{repair_id}/publish-pr", status_code=status.HTTP_202_ACCEPTED
)
async def publish_pr(
    repair_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
    request: Request,
) -> dict[str, Any]:
    detail = await RepairsRepository(session).detail_for_org(
        repair_id, ctx.org_id
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repair not found"
        )
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="repair.publish_pr",
        target_type="repair",
        target_id=str(repair_id),
    )
    await session.commit()
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        try:
            await queue.enqueue_job("publish_pr", str(repair_id))
        except Exception:
            pass
    return {"repair_id": str(repair_id), "status": "queued"}
