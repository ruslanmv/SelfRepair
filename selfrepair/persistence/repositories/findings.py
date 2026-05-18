"""Repository for findings.

`upsert_by_fingerprint` is the load-bearing method: same vuln seen across runs
collapses to one row, with `last_seen_sha` and `last_seen_at` updated.

The console list endpoint pages findings keyset-style on
`(last_seen_at DESC, id DESC)`. That ordering is what the operator
actually wants — "what changed most recently?" — and it stays stable as
new runs upsert older fingerprints to a newer `last_seen_at`.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import Finding as FindingRow, FindingStatus
from selfrepair.sdk.models import Finding as FindingPayload


class FindingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --------------------------- writes (worker) ---------------------------

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

    # --------------------------- reads (api) -------------------------------

    async def get(self, finding_id: uuid.UUID) -> FindingRow | None:
        return await self._session.get(FindingRow, finding_id)

    async def get_for_org(
        self, finding_id: uuid.UUID, org_id: uuid.UUID
    ) -> FindingRow | None:
        stmt = select(FindingRow).where(
            FindingRow.id == finding_id, FindingRow.org_id == org_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

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

    async def list_for_org(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None = None,
        severity: str | None = None,
        kind: str | None = None,
        status: FindingStatus | None = None,
        q: str | None = None,
        limit: int = 50,
        after_last_seen_at: datetime | None = None,
        after_id: uuid.UUID | None = None,
    ) -> list[FindingRow]:
        """Page over findings with the filters the console exposes.

        Keyset pagination on `(last_seen_at DESC, id DESC)`. Pass the
        last item's pair back as `after_*` to fetch the next page.
        """
        stmt = (
            select(FindingRow)
            .where(FindingRow.org_id == org_id)
            .order_by(FindingRow.last_seen_at.desc(), FindingRow.id.desc())
            .limit(limit)
        )
        if repo_id is not None:
            stmt = stmt.where(FindingRow.repo_id == repo_id)
        if severity is not None:
            stmt = stmt.where(FindingRow.severity == severity)
        if kind is not None:
            stmt = stmt.where(FindingRow.kind == kind)
        if status is not None:
            stmt = stmt.where(FindingRow.status == status)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    FindingRow.kind.ilike(like),
                    FindingRow.fingerprint.ilike(like),
                    FindingRow.cwe.ilike(like),
                    FindingRow.cve.ilike(like),
                )
            )
        if after_last_seen_at is not None and after_id is not None:
            stmt = stmt.where(
                or_(
                    FindingRow.last_seen_at < after_last_seen_at,
                    and_(
                        FindingRow.last_seen_at == after_last_seen_at,
                        FindingRow.id < after_id,
                    ),
                )
            )
        return list((await self._session.execute(stmt)).scalars())

    # --------------------------- mutations (api) ---------------------------

    async def mark_fixed(self, finding_id: uuid.UUID) -> None:
        finding = await self.get(finding_id)
        if finding is None:
            raise LookupError(f"finding {finding_id} not found")
        finding.status = FindingStatus.FIXED

    async def suppress(
        self,
        finding_id: uuid.UUID,
        *,
        reason: str | None,
        until: datetime | None = None,
    ) -> FindingRow:
        finding = await self.get(finding_id)
        if finding is None:
            raise LookupError(f"finding {finding_id} not found")
        finding.status = FindingStatus.SUPPRESSED
        finding.suppressed_reason = reason
        finding.suppressed_until = until
        return finding
