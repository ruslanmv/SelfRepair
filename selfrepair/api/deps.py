"""Shared FastAPI dependencies for the SelfRepair `/v1` API.

`CtxDep` is the single source of truth for tenant scope. It prefers
the values the auth middleware (M11/M12) writes onto `request.state`,
and falls back to an `X-SelfRepair-Org-Id` header (dev only) or the
`SELFREPAIR_DEV_ORG_ID` env var. Routes never read tenancy from query
parameters or request bodies.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from selfrepair.persistence import get_sessionmaker

_DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://selfrepair:selfrepair@localhost/selfrepair"
)
_DEFAULT_DEV_ORG_ID = "00000000-0000-0000-0000-000000000001"


def get_database_url() -> str:
    return os.getenv("SELFREPAIR_DATABASE_URL", _DEFAULT_DATABASE_URL)


def get_app_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return get_sessionmaker(get_database_url())


async def db_session() -> AsyncIterator[AsyncSession]:
    sessionmaker = get_app_sessionmaker()
    async with sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(db_session)]


# ----------------------------- request context -----------------------------


@dataclass(frozen=True)
class RequestContext:
    org_id: uuid.UUID
    user_id: uuid.UUID | None
    actor: str | None


def _resolve_org(
    request: Request,
    x_selfrepair_org_id: str | None = Header(default=None, alias="X-SelfRepair-Org-Id"),
) -> uuid.UUID:
    # 1. Authenticated session takes precedence.
    session_org_id = getattr(request.state, "session_org_id", None)
    if session_org_id is not None:
        return session_org_id
    # 2. Dev escape-hatch via header / env. Production must reject
    #    requests without a session; that gate lands with the
    #    enforce-auth middleware in M6 hardening.
    raw = (
        x_selfrepair_org_id
        or os.getenv("SELFREPAIR_DEV_ORG_ID")
        or _DEFAULT_DEV_ORG_ID
    )
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid org_id",
        ) from exc


def request_context(
    request: Request,
    org_id: uuid.UUID = Depends(_resolve_org),
    x_selfrepair_actor: str | None = Header(default=None, alias="X-SelfRepair-Actor"),
) -> RequestContext:
    user_id = getattr(request.state, "session_user_id", None)
    actor = x_selfrepair_actor or (str(user_id) if user_id else None)
    return RequestContext(org_id=org_id, user_id=user_id, actor=actor)


CtxDep = Annotated[RequestContext, Depends(request_context)]


# ------------------------------- pagination --------------------------------


MAX_LIMIT = 500
DEFAULT_LIMIT = 50


@dataclass(frozen=True)
class Pagination:
    limit: int
    cursor: dict[str, Any] | None


def encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(token: str) -> dict[str, Any]:
    try:
        padding = b"=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token.encode("ascii") + padding)
        decoded = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=400, detail="invalid cursor")
    return decoded


def pagination(
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Pagination:
    if limit < 1 or limit > MAX_LIMIT:
        raise HTTPException(
            status_code=400, detail=f"limit must be between 1 and {MAX_LIMIT}"
        )
    return Pagination(
        limit=limit,
        cursor=decode_cursor(cursor) if cursor else None,
    )


PageDep = Annotated[Pagination, Depends(pagination)]


__all__ = [
    "CtxDep",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "Pagination",
    "PageDep",
    "RequestContext",
    "SessionDep",
    "db_session",
    "decode_cursor",
    "encode_cursor",
    "get_app_sessionmaker",
    "get_database_url",
    "request_context",
]
