"""`/v1/auth`, `/v1/me`, `/v1/orgs/current` — password login + session.

MVP scope: email + password, single-org users. SSO/SCIM/RBAC are
separate milestones. The API ships everything an SPA needs to hide a
Login page behind a real session: login mints a cookie session,
logout revokes it, refresh extends it, /me returns the resolved
user+org.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from selfrepair.api.deps import SessionDep
from selfrepair.auth.cookies import (
    COOKIE_NAME,
    clear_session_cookie,
    set_session_cookie,
)
from selfrepair.auth.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
)
from selfrepair.auth.sessions import (
    DEFAULT_SESSION_TTL,
    create_session,
    extend_session,
    lookup_session,
    revoke_session,
)
from selfrepair.persistence.auth_models import UserCredential
from selfrepair.persistence.models import Org, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    org_id: uuid.UUID | None = Field(
        default=None,
        description="Required only if the email is shared across orgs.",
    )


def _serialize_user(user: User, org: Org) -> dict[str, Any]:
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "role": (
                user.role.value if hasattr(user.role, "value") else user.role
            ),
        },
        "org": {
            "id": str(org.id),
            "name": org.name,
            "plan": org.plan,
        },
    }


async def _find_user(session, email: str, org_id: uuid.UUID | None):
    stmt = select(User).where(User.email == email)
    if org_id is not None:
        stmt = stmt.where(User.org_id == org_id)
    rows = list((await session.execute(stmt)).scalars())
    return rows


async def _find_org(session, org_id: uuid.UUID) -> Org | None:
    return await session.get(Org, org_id)


@router.post("/v1/auth/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> dict[str, Any]:
    candidates = await _find_user(session, body.email, body.org_id)
    if not candidates:
        # Same response shape as bad-password to avoid email enumeration.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    if len(candidates) > 1 and body.org_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "email is associated with multiple organisations; "
                "specify org_id"
            ),
        )
    user = candidates[0]
    cred = await session.get(UserCredential, user.id)
    if cred is None or not verify_password(
        cred.password_hash, body.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    # Opportunistic rehash on weak parameters.
    if needs_rehash(cred.password_hash):
        cred.password_hash = hash_password(body.password)

    org = await _find_org(session, user.org_id)
    if org is None:
        # Defensive: a user without an org row is corrupt state.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user has no org",
        )

    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    token, _row = await create_session(
        session,
        org_id=user.org_id,
        user_id=user.id,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    set_session_cookie(
        response,
        token,
        max_age_seconds=int(DEFAULT_SESSION_TTL.total_seconds()),
    )
    return _serialize_user(user, org)


@router.post("/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        row = await lookup_session(session, token)
        if row is not None:
            await revoke_session(session, row)
            await session.commit()
    clear_session_cookie(response)


@router.post("/v1/auth/refresh")
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
) -> dict[str, Any]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="no session",
        )
    row = await lookup_session(session, token)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session expired",
        )
    await extend_session(session, row)
    await session.commit()
    set_session_cookie(
        response,
        token,
        max_age_seconds=int(DEFAULT_SESSION_TTL.total_seconds()),
    )
    return {
        "expires_at": row.expires_at.isoformat(),
        "last_seen_at": row.last_seen_at.isoformat(),
    }


@router.get("/v1/me")
async def get_me(
    request: Request,
    session: SessionDep,
) -> dict[str, Any]:
    user_id = getattr(request.state, "session_user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found"
        )
    org = await session.get(Org, user.org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user has no org",
        )
    return _serialize_user(user, org)


@router.get("/v1/orgs/current")
async def get_current_org(
    request: Request,
    session: SessionDep,
) -> dict[str, Any]:
    org_id = getattr(request.state, "session_org_id", None)
    if org_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    org = await session.get(Org, org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="org not found"
        )
    return {
        "id": str(org.id),
        "name": org.name,
        "plan": org.plan,
        "created_at": org.created_at.isoformat(),
    }
