"""`/v1/policies` — bundle versions and decision log.

The full OPA bundle bytes live in object storage; this surface manages
pointers + metadata. `POST /evaluate` is a thin shim today (echoes
input so the SPA can wire its UI flow) and gets a real OPA call once
the policy engine integration lands.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from selfrepair.api.deps import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CtxDep,
    SessionDep,
    decode_cursor,
    encode_cursor,
)
from selfrepair.persistence.console_models import PolicyBundleVersion
from selfrepair.persistence.models import PolicyDecision
from selfrepair.persistence.repositories.policies import PoliciesRepository

router = APIRouter(prefix="/v1/policies", tags=["policies"])


def _serialize_version(v: PolicyBundleVersion) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "org_id": str(v.org_id),
        "version": v.version,
        "description": v.description,
        "bundle_sha": v.bundle_sha,
        "bundle_object_url": v.bundle_object_url,
        "created_by": str(v.created_by) if v.created_by else None,
        "created_at": v.created_at.isoformat(),
        "deployed_at": v.deployed_at.isoformat() if v.deployed_at else None,
    }


def _serialize_decision(d: PolicyDecision) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "repair_id": str(d.repair_id),
        "rule_id": d.rule_id,
        "outcome": d.outcome,
        "requires_approval": d.requires_approval,
        "approver_id": str(d.approver_id) if d.approver_id else None,
        "decided_at": d.decided_at.isoformat() if d.decided_at else None,
    }


@router.get("")
async def list_policies(
    ctx: CtxDep,
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    after_created_at: datetime | None = None
    if cursor:
        c = decode_cursor(cursor)
        if c.get("after_created_at"):
            try:
                after_created_at = datetime.fromisoformat(c["after_created_at"])
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="invalid cursor"
                ) from exc
    rows = await PoliciesRepository(session).list_versions(
        org_id=ctx.org_id, limit=limit + 1, after_created_at=after_created_at
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor({"after_created_at": page[-1].created_at.isoformat()})
        if has_more and page
        else None
    )
    return {
        "items": [_serialize_version(v) for v in page],
        "count": len(page),
        "next_cursor": next_cursor,
    }


@router.get("/{policy_id}")
async def get_policy(
    policy_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    v = await PoliciesRepository(session).get_version(policy_id, ctx.org_id)
    if v is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="policy not found"
        )
    return _serialize_version(v)


class PolicyBundleUpload(BaseModel):
    version: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    bundle_sha: str = Field(..., min_length=8, max_length=64)
    bundle_object_url: str = Field(..., min_length=1, max_length=1024)


@router.put("/bundle", status_code=status.HTTP_201_CREATED)
async def upload_bundle(
    body: PolicyBundleUpload,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    v = await PoliciesRepository(session).create_version(
        org_id=ctx.org_id,
        version=body.version,
        description=body.description,
        bundle_sha=body.bundle_sha,
        bundle_object_url=body.bundle_object_url,
        created_by=ctx.user_id,
    )
    await session.commit()
    return _serialize_version(v)


class EvaluateRequest(BaseModel):
    input: dict[str, Any]
    rule_id: str | None = None


@router.post("/evaluate")
async def evaluate_policy(body: EvaluateRequest) -> dict[str, Any]:
    """Stub evaluator.

    Returns a deterministic shape so the SPA can wire its UI flow today.
    Replaced with a real OPA roundtrip when the policy engine adapter
    lands; the response shape stays stable.
    """
    return {
        "rule_id": body.rule_id or "default",
        "outcome": "allow",
        "requires_approval": False,
        "reasons": [],
        "input_echo": body.input,
        "engine": "stub-v0",
    }


@router.get("/decisions")
async def list_policy_decisions(
    ctx: CtxDep,
    session: SessionDep,
    repair_id: uuid.UUID | None = Query(default=None),
    outcome: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    after_id: uuid.UUID | None = None
    if cursor:
        c = decode_cursor(cursor)
        if c.get("after_id"):
            try:
                after_id = uuid.UUID(c["after_id"])
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="invalid cursor"
                ) from exc
    rows = await PoliciesRepository(session).list_decisions(
        org_id=ctx.org_id,
        repair_id=repair_id,
        outcome=outcome,
        limit=limit + 1,
        after_id=after_id,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor({"after_id": str(page[-1].id)})
        if has_more and page
        else None
    )
    return {
        "items": [_serialize_decision(d) for d in page],
        "count": len(page),
        "next_cursor": next_cursor,
    }
