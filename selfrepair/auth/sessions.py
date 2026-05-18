"""Cookie-session management.

A login creates a `session` row with a hashed token; the cookie
carries the plaintext token, the DB stores `sha256(token)`. Every
request's middleware looks up by hash and updates `last_seen_at`.
Logout flips `revoked_at`; refresh extends `expires_at`.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.console_models import Session

DEFAULT_SESSION_TTL = timedelta(days=7)


def generate_token() -> str:
    """32 url-safe bytes = 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    ip: str | None = None,
    user_agent: str | None = None,
    ttl: timedelta = DEFAULT_SESSION_TTL,
) -> tuple[str, Session]:
    token = generate_token()
    row = Session(
        org_id=org_id,
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + ttl,
        ip=ip,
        user_agent=user_agent,
    )
    session.add(row)
    await session.flush()
    return token, row


async def lookup_session(
    session: AsyncSession, token: str
) -> Session | None:
    if not token:
        return None
    stmt = select(Session).where(Session.token_hash == hash_token(token))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    if row.revoked_at is not None:
        return None
    if row.expires_at <= datetime.now(UTC):
        return None
    return row


async def touch_session(session: AsyncSession, row: Session) -> None:
    row.last_seen_at = datetime.now(UTC)
    await session.flush()


async def extend_session(
    session: AsyncSession,
    row: Session,
    *,
    ttl: timedelta = DEFAULT_SESSION_TTL,
) -> None:
    now = datetime.now(UTC)
    row.expires_at = now + ttl
    row.last_seen_at = now
    await session.flush()


async def revoke_session(session: AsyncSession, row: Session) -> None:
    row.revoked_at = datetime.now(UTC)
    await session.flush()
