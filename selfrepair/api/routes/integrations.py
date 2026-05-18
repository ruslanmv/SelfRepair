"""`/v1/integrations` — GitHub / GitLab / Hugging Face connections.

`credential_ref` is a pointer into the secret manager (env name, KMS
ARN, Vault path). The actual token is never sent to the API in the
create body; the integration UI hands over a reference, not bytes.
Delete is soft so audit references stay valid.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from selfrepair.api.deps import CtxDep, SessionDep
from selfrepair.persistence.console_models import (
    IntegrationConnection,
    IntegrationStatus,
)
from selfrepair.persistence.repositories.integrations import (
    IntegrationsRepository,
)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])

_ALLOWED_PROVIDERS = {"github", "gitlab", "huggingface", "bitbucket"}


def _serialize(c: IntegrationConnection) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "org_id": str(c.org_id),
        "provider": c.provider,
        "display_name": c.display_name,
        "account": c.account,
        "status": (
            c.status.value if hasattr(c.status, "value") else c.status
        ),
        # Never expose the credential itself; the ref alone is enough
        # for the UI to show "connected via secret 'gh-pat'".
        "credential_ref": c.credential_ref,
        "config": c.config,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
        "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
    }


class ConnectRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    account: str | None = Field(default=None, max_length=255)
    credential_ref: str = Field(..., min_length=1, max_length=512)
    config: dict[str, Any] | None = None


@router.get("")
async def list_integrations(
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    rows = await IntegrationsRepository(session).list_for_org(org_id=ctx.org_id)
    return {"items": [_serialize(r) for r in rows], "count": len(rows)}


@router.get("/{integration_id}")
async def get_integration(
    integration_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    row = await IntegrationsRepository(session).get_for_org(
        integration_id, ctx.org_id
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="integration not found",
        )
    return _serialize(row)


@router.post("/{provider}/connect", status_code=status.HTTP_201_CREATED)
async def connect_integration(
    provider: str,
    body: ConnectRequest,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    if provider not in _ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported provider: {provider}",
        )
    row = await IntegrationsRepository(session).create(
        org_id=ctx.org_id,
        provider=provider,
        display_name=body.display_name,
        credential_ref=body.credential_ref,
        account=body.account,
        config=body.config,
        status=IntegrationStatus.PENDING,
    )
    await session.commit()
    return _serialize(row)


@router.delete(
    "/{integration_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def disconnect_integration(
    integration_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> None:
    repo = IntegrationsRepository(session)
    row = await repo.get_for_org(integration_id, ctx.org_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="integration not found",
        )
    await repo.soft_delete(row)
    await session.commit()
