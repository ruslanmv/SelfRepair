"""Repository for the append-only `audit_log` table.

Writes are intentionally narrow: every row is `(org_id, actor, action,
target_type, target_id, ip?, payload?)`. The route layer is the only
caller that should `record()` a row — the worker writes its own audit
through job_event so the audit_log stays focused on operator actions.

Reads support the three patterns the SPA needs:

* a fleet-wide log filtered by actor / action / target_type / time range
* a per-resource trace (`scope_for(scope, scope_id)`) for the
  AuditLogDrawer
* a streaming export for compliance use cases (NDJSON, time-bounded).
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---------------------------- writes ----------------------------

    async def record(
        self,
        *,
        org_id: uuid.UUID,
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        ip: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        row = AuditLog(
            org_id=org_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip=ip,
            payload=payload,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    # ---------------------------- reads -----------------------------

    async def get_for_org(
        self, audit_id: int, org_id: uuid.UUID
    ) -> AuditLog | None:
        stmt = select(AuditLog).where(
            AuditLog.id == audit_id, AuditLog.org_id == org_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_org(
        self,
        *,
        org_id: uuid.UUID,
        actor: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        after_id: int | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Newest-first id-cursor pagination.

        `audit_log.id` is monotonic and append-only, so an id keyset is
        both stable and trivially comparable across mirrors/replicas.
        """
        stmt = (
            select(AuditLog)
            .where(AuditLog.org_id == org_id)
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if target_type:
            stmt = stmt.where(AuditLog.target_type == target_type)
        if since:
            stmt = stmt.where(AuditLog.ts >= since)
        if until:
            stmt = stmt.where(AuditLog.ts < until)
        if after_id is not None:
            stmt = stmt.where(AuditLog.id < after_id)
        return list((await self._session.execute(stmt)).scalars())

    async def list_for_scope(
        self,
        *,
        org_id: uuid.UUID,
        scope: str,
        scope_id: str,
        limit: int = 100,
        after_id: int | None = None,
    ) -> list[AuditLog]:
        return await self.list_for_org(
            org_id=org_id,
            target_type=scope,
            limit=limit,
            after_id=after_id,
        ) if False else await self._list_for_scope(
            org_id=org_id,
            scope=scope,
            scope_id=scope_id,
            limit=limit,
            after_id=after_id,
        )

    async def _list_for_scope(
        self,
        *,
        org_id: uuid.UUID,
        scope: str,
        scope_id: str,
        limit: int,
        after_id: int | None,
    ) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.org_id == org_id,
                AuditLog.target_type == scope,
                AuditLog.target_id == scope_id,
            )
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
        if after_id is not None:
            stmt = stmt.where(AuditLog.id < after_id)
        return list((await self._session.execute(stmt)).scalars())

    async def iter_for_export(
        self,
        *,
        org_id: uuid.UUID,
        since: datetime | None = None,
        until: datetime | None = None,
        chunk_size: int = 500,
    ) -> AsyncIterator[AuditLog]:
        """Yield audit rows in oldest-first order for streaming exports.

        Drives a chunked id-keyset scan so a multi-million-row export
        doesn't materialise in memory. Order is `id ASC` so consumers
        can resume from the last id they saw.
        """
        cursor: int = 0
        while True:
            stmt = (
                select(AuditLog)
                .where(AuditLog.org_id == org_id)
                .where(AuditLog.id > cursor)
                .order_by(AuditLog.id.asc())
                .limit(chunk_size)
            )
            if since:
                stmt = stmt.where(AuditLog.ts >= since)
            if until:
                stmt = stmt.where(AuditLog.ts < until)
            rows = list(
                (await self._session.execute(stmt)).scalars()
            )
            if not rows:
                return
            for row in rows:
                yield row
            cursor = rows[-1].id
            if len(rows) < chunk_size:
                return
