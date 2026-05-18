"""`/v1/findings` — fleet-wide vulnerability listing, detail, and mutations.

Mutating endpoints record an audit row on every state change so the
operator's compliance trail is complete; `run-repair` creates a Job
row + enqueues `process_job` (best-effort).
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
from selfrepair.persistence.models import Finding, FindingStatus, JobTrigger
from selfrepair.persistence.repositories.audit import AuditRepository
from selfrepair.persistence.repositories.findings import FindingsRepository
from selfrepair.persistence.repositories.jobs import JobsRepository

router = APIRouter(prefix="/v1/findings", tags=["findings"])


def _serialize(f: Finding) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "org_id": str(f.org_id),
        "repo_id": str(f.repo_id),
        "fingerprint": f.fingerprint,
        "kind": f.kind,
        "severity": f.severity,
        "cwe": f.cwe,
        "cve": f.cve,
        "first_seen_sha": f.first_seen_sha,
        "last_seen_sha": f.last_seen_sha,
        "first_seen_at": f.first_seen_at.isoformat(),
        "last_seen_at": f.last_seen_at.isoformat(),
        "status": f.status.value if hasattr(f.status, "value") else f.status,
        "suppressed_until": (
            f.suppressed_until.isoformat() if f.suppressed_until else None
        ),
        "suppressed_reason": f.suppressed_reason,
        "metadata": f.extra,
    }


@router.get("")
async def list_findings(
    ctx: CtxDep,
    session: SessionDep,
    repo_id: uuid.UUID | None = Query(default=None),
    severity: str | None = Query(default=None, max_length=16),
    kind: str | None = Query(default=None, max_length=255),
    status_filter: str | None = Query(default=None, alias="status", max_length=16),
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    after_last_seen_at: datetime | None = None
    after_id: uuid.UUID | None = None
    if cursor:
        c = decode_cursor(cursor)
        try:
            if c.get("after_last_seen_at"):
                after_last_seen_at = datetime.fromisoformat(c["after_last_seen_at"])
            if c.get("after_id"):
                after_id = uuid.UUID(c["after_id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc

    parsed_status: FindingStatus | None = None
    if status_filter:
        try:
            parsed_status = FindingStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid status: {status_filter}"
            ) from exc

    repo = FindingsRepository(session)
    rows = await repo.list_for_org(
        org_id=ctx.org_id,
        repo_id=repo_id,
        severity=severity,
        kind=kind,
        status=parsed_status,
        q=q,
        limit=limit + 1,
        after_last_seen_at=after_last_seen_at,
        after_id=after_id,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor(
            {
                "after_last_seen_at": page[-1].last_seen_at.isoformat(),
                "after_id": str(page[-1].id),
            }
        )
        if has_more and page
        else None
    )
    return {
        "items": [_serialize(r) for r in page],
        "count": len(page),
        "next_cursor": next_cursor,
    }


@router.get("/{finding_id}")
async def get_finding(
    finding_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    f = await FindingsRepository(session).get_for_org(finding_id, ctx.org_id)
    if f is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="finding not found"
        )
    return _serialize(f)


# ----------------------------- mutations -----------------------------


class SuppressBody(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    until: datetime | None = None


@router.post("/{finding_id}/suppress")
async def suppress_finding(
    finding_id: uuid.UUID,
    body: SuppressBody,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    repo = FindingsRepository(session)
    f = await repo.get_for_org(finding_id, ctx.org_id)
    if f is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="finding not found"
        )
    await repo.suppress(finding_id, reason=body.reason, until=body.until)
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="finding.suppress",
        target_type="finding",
        target_id=str(finding_id),
        payload={"reason": body.reason} if body.reason else None,
    )
    await session.commit()
    return _serialize(f)


@router.post("/{finding_id}/mark-fixed")
async def mark_finding_fixed(
    finding_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    repo = FindingsRepository(session)
    f = await repo.get_for_org(finding_id, ctx.org_id)
    if f is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="finding not found"
        )
    await repo.mark_fixed(finding_id)
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="finding.mark_fixed",
        target_type="finding",
        target_id=str(finding_id),
    )
    await session.commit()
    return _serialize(f)


@router.post(
    "/{finding_id}/run-repair", status_code=status.HTTP_202_ACCEPTED
)
async def run_repair_for_finding(
    finding_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
    request: Request,
) -> dict[str, Any]:
    findings_repo = FindingsRepository(session)
    f = await findings_repo.get_for_org(finding_id, ctx.org_id)
    if f is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="finding not found"
        )
    job = await JobsRepository(session).create(
        org_id=ctx.org_id,
        repo_id=f.repo_id,
        trigger=JobTrigger.MANUAL,
    )
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="finding.run_repair",
        target_type="finding",
        target_id=str(finding_id),
        payload={"job_id": str(job.id)},
    )
    await session.commit()
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        try:
            await queue.enqueue_job("process_job", str(job.id))
        except Exception:
            pass
    return {"job_id": str(job.id), "finding_id": str(finding_id)}
