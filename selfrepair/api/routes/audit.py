"""`/v1/audit` — append-only audit log: list, detail, scope, export.

Read-only: writes are produced by mutating endpoints elsewhere
(approve/reject/cancel etc.) once those land in the mutation batch.
Until then this surface is useful for the Job/Repair audit drawers and
the operator's compliance export workflow.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from selfrepair.api.deps import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CtxDep,
    SessionDep,
    decode_cursor,
    encode_cursor,
    get_app_sessionmaker,
)
from selfrepair.persistence.models import AuditLog
from selfrepair.persistence.repositories.audit import AuditRepository

router = APIRouter(prefix="/v1/audit", tags=["audit"])


def _serialize(row: AuditLog) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "org_id": str(row.org_id),
        "actor": row.actor,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "ts": row.ts.isoformat(),
        "ip": row.ip,
        "payload": row.payload,
    }


@router.get("")
async def list_audit(
    ctx: CtxDep,
    session: SessionDep,
    actor: str | None = Query(default=None, max_length=255),
    action: str | None = Query(default=None, max_length=64),
    target_type: str | None = Query(default=None, max_length=64),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    after_id: int | None = None
    if cursor:
        c = decode_cursor(cursor)
        try:
            after_id = (
                int(c["after_id"]) if c.get("after_id") is not None else None
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid cursor payload",
            ) from exc

    rows = await AuditRepository(session).list_for_org(
        org_id=ctx.org_id,
        actor=actor,
        action=action,
        target_type=target_type,
        since=since,
        until=until,
        after_id=after_id,
        limit=limit + 1,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor({"after_id": int(page[-1].id)})
        if has_more and page
        else None
    )
    return {
        "items": [_serialize(r) for r in page],
        "count": len(page),
        "next_cursor": next_cursor,
    }


@router.get("/{audit_id}")
async def get_audit(
    audit_id: int,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    row = await AuditRepository(session).get_for_org(audit_id, ctx.org_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="audit row not found",
        )
    return _serialize(row)


@router.get("/scopes/{scope}/{scope_id}")
async def list_audit_for_scope(
    scope: str,
    scope_id: str,
    ctx: CtxDep,
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    """Per-resource audit trace.

    `scope` is the `target_type` written by the API mutation layer
    (`job`, `repair`, `finding`, `repo`, ...). `scope_id` is the
    matching string-form UUID/id. Used by `AuditLogDrawer.jsx`.
    """
    after_id: int | None = None
    if cursor:
        c = decode_cursor(cursor)
        try:
            after_id = (
                int(c["after_id"]) if c.get("after_id") is not None else None
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid cursor payload",
            ) from exc
    rows = await AuditRepository(session).list_for_scope(
        org_id=ctx.org_id,
        scope=scope,
        scope_id=scope_id,
        after_id=after_id,
        limit=limit + 1,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor({"after_id": int(page[-1].id)})
        if has_more and page
        else None
    )
    return {
        "scope": scope,
        "scope_id": scope_id,
        "items": [_serialize(r) for r in page],
        "count": len(page),
        "next_cursor": next_cursor,
    }


@router.get("/export")
async def export_audit(
    ctx: CtxDep,
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> StreamingResponse:
    """Stream audit rows as newline-delimited JSON.

    Used by compliance pipelines that ingest audit data into a SIEM or
    data warehouse. Order is oldest-first so consumers can resume from
    the last `id` they wrote without missing rows.
    """
    sessionmaker = get_app_sessionmaker()
    org_id = ctx.org_id

    async def gen():
        import json

        async with sessionmaker() as session:
            repo = AuditRepository(session)
            async for row in repo.iter_for_export(
                org_id=org_id, since=since, until=until
            ):
                yield (json.dumps(_serialize(row), default=str) + "\n").encode(
                    "utf-8"
                )

    filename = "selfrepair-audit"
    if since:
        filename += f"-from-{since.date().isoformat()}"
    if until:
        filename += f"-to-{until.date().isoformat()}"
    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.ndjson"',
            "Cache-Control": "no-store",
        },
    )
