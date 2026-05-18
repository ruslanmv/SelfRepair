"""Repository for `integration_connection`.

Deletes are soft (set `deleted_at`) so the audit log keeps referring to
a live row long after the operator revokes a token. The credential
itself lives in the secret manager; this row only carries the opaque
`credential_ref`.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.console_models import (
    IntegrationConnection,
    IntegrationStatus,
)


class IntegrationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_org(
        self,
        *,
        org_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> list[IntegrationConnection]:
        stmt = (
            select(IntegrationConnection)
            .where(IntegrationConnection.org_id == org_id)
            .order_by(IntegrationConnection.created_at.desc())
        )
        if not include_deleted:
            stmt = stmt.where(IntegrationConnection.deleted_at.is_(None))
        return list((await self._session.execute(stmt)).scalars())

    async def get_for_org(
        self, integration_id: uuid.UUID, org_id: uuid.UUID
    ) -> IntegrationConnection | None:
        stmt = select(IntegrationConnection).where(
            IntegrationConnection.id == integration_id,
            IntegrationConnection.org_id == org_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        org_id: uuid.UUID,
        provider: str,
        display_name: str,
        credential_ref: str,
        account: str | None = None,
        config: dict[str, Any] | None = None,
        status: IntegrationStatus = IntegrationStatus.PENDING,
    ) -> IntegrationConnection:
        row = IntegrationConnection(
            org_id=org_id,
            provider=provider,
            display_name=display_name,
            credential_ref=credential_ref,
            account=account,
            config=config,
            status=status,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def soft_delete(self, integration: IntegrationConnection) -> None:
        integration.deleted_at = datetime.now(UTC)
        integration.status = IntegrationStatus.REVOKED
        await self._session.flush()
