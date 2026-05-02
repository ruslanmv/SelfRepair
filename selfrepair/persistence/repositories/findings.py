"""Repository for findings.

`upsert_by_fingerprint` is the load-bearing method: same vuln seen across runs
collapses to one row, with `last_seen_sha` and `last_seen_at` updated.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import Finding as FindingRow, FindingStatus
from selfrepair.sdk.models import Finding as FindingPayload


class FindingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_by_fingerprint(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        sha: str | None,
        finding: FindingPayload,
    ) -> FindingRow:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(FindingRow)
            .values(
                org_id=org_id,
                repo_id=repo_id,
                fingerprint=finding.fingerprint,
                kind=finding.kind,
                severity=finding.severity.value,
                cwe=finding.cwe,
                cve=finding.cve,
                first_seen_sha=sha,
                last_seen_sha=sha,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_finding_fingerprint",
                set_={
                    "last_seen_sha": sha,
                    "last_seen_at": now,
                    "severity": finding.severity.value,
                },
            )
            .returning(FindingRow)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def get(self, finding_id: uuid.UUID) -> FindingRow | None:
        return await self._session.get(FindingRow, finding_id)

    async def list_open_for_repo(self, repo_id: uuid.UUID) -> list[FindingRow]:
        stmt = (
            select(FindingRow)
            .where(
                FindingRow.repo_id == repo_id,
                FindingRow.status == FindingStatus.OPEN,
            )
            .order_by(FindingRow.first_seen_at)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def mark_fixed(self, finding_id: uuid.UUID) -> None:
        finding = await self.get(finding_id)
        if finding is None:
            raise LookupError(f"finding {finding_id} not found")
        finding.status = FindingStatus.FIXED
