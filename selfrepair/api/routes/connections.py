"""`/v1/connections` — OllaBridge, GitPilot, and MatrixLab setup.

The browser receives status only. Device tokens and service tokens are
encrypted before they are written and are not included in responses.

Organization scope comes from the session. A caller cannot read or write
another organization's row by changing the request body.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.api.deps import CtxDep, SessionDep
from selfrepair.connectors.runtime import load_saved_connector
from selfrepair.connectors.service import (
    CLOUD_API_BASE,
    CLOUD_PAIR_URL,
    DEFAULTS,
    PROVIDERS,
    ConnectorError,
    ConnectorState,
    apply_disconnect,
    apply_probe,
    assert_mutation_origin,
    encrypt,
    ensure_encryption_configured,
    interpret_pairing_response,
    merged_secret,
    normalize_pairing_code,
    pairing_request_body,
    pairing_submission,
    probe_provider,
    public_view,
    rate_limit,
    response_payload,
    validate_service_url,
)
from selfrepair.persistence.connector_models import ServiceConnection
from selfrepair.persistence.models import User
from selfrepair.persistence.repositories.audit import AuditRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/connections", tags=["connections"])

_DEV_ENVS = {"dev", "test", "local", "ci"}
_PAIR_LIMIT = 5
_PAIR_WINDOW = 600


class SaveConnectionBody(BaseModel):
    base_url: str | None = None
    api_key: str | None = Field(default=None, max_length=4096)


class PairBody(BaseModel):
    code: str = Field(..., max_length=32)


def _http_error(exc: ConnectorError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _role_value(user: User) -> str:
    role = user.role
    return role.value if hasattr(role, "value") else str(role)


async def _authorize(request: Request, ctx: CtxDep, session: AsyncSession, *, write: bool) -> str:
    if write:
        host = request.headers.get("host") or request.url.netloc
        try:
            assert_mutation_origin(request.headers, host=host)
        except ConnectorError as exc:
            raise _http_error(exc) from exc
    env = os.getenv("SELFREPAIR_ENV", "").strip().lower()
    dev = env in _DEV_ENVS or os.getenv("SELFREPAIR_INSECURE_COOKIES") == "1"
    user_id = getattr(request.state, "session_user_id", None)
    session_org = getattr(request.state, "session_org_id", None)
    if user_id is None:
        if dev:
            return "dev"
        raise HTTPException(status_code=401, detail="Not authenticated")
    if session_org is not None and session_org != ctx.org_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    user = await session.get(User, user_id)
    if user is None or user.org_id != ctx.org_id:
        raise HTTPException(status_code=403, detail="Not allowed")
    if write and _role_value(user) != "admin":
        raise HTTPException(status_code=403, detail="Admin access required to change connectors")
    return str(user_id)


async def _load(
    session: AsyncSession, org_id: uuid.UUID, provider: str
) -> ServiceConnection | None:
    stmt = select(ServiceConnection).where(
        ServiceConnection.org_id == org_id,
        ServiceConnection.provider == provider,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _state_from_row(row: ServiceConnection | None, provider: str) -> ConnectorState | None:
    if row is None:
        return None
    try:
        secret = decrypt_row(row.secret_enc)
    except ConnectorError as exc:
        raise _http_error(exc) from exc
    return ConnectorState(
        provider=provider,
        base_url=row.base_url or DEFAULTS.get(provider, ""),
        secret=secret,
        status=row.status or "unknown",
        detail=row.detail or "",
        auth_method=row.auth_method,
        last_checked_at=row.last_checked_at,
        last_attempted_at=row.last_attempted_at,
    )


def decrypt_row(stored: str | None) -> str:
    from selfrepair.connectors.service import decrypt

    return decrypt(stored or "")


def _write_row(row: ServiceConnection, state: ConnectorState) -> None:
    if state.secret:
        ensure_encryption_configured()
        row.secret_enc = encrypt(state.secret)
    else:
        row.secret_enc = None
    row.base_url = state.base_url
    row.status = state.status
    row.detail = state.detail[:2000]
    row.auth_method = state.auth_method
    row.last_checked_at = state.last_checked_at
    row.last_attempted_at = state.last_attempted_at
    row.updated_at = (
        datetime.now(tz=state.last_attempted_at.tzinfo)
        if state.last_attempted_at
        else row.updated_at
    )


async def _audit(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor: str,
    action: str,
    provider: str,
    status: str,
    request: Request,
) -> None:
    await AuditRepository(session).record(
        org_id=org_id,
        actor=actor,
        action=action,
        target_type="service_connection",
        target_id=provider,
        ip=request.client.host if request.client else None,
        payload={"provider": provider, "status": status},
    )


async def _blank(session: AsyncSession, org_id: uuid.UUID, provider: str) -> ServiceConnection:
    row = ServiceConnection(
        org_id=org_id,
        provider=provider,
        base_url=DEFAULTS[provider],
        status="unknown",
        detail="",
    )
    session.add(row)
    await session.flush()
    return row


@router.get("")
async def list_connections(
    request: Request, ctx: CtxDep, session: SessionDep
) -> list[dict[str, Any]]:
    await _authorize(request, ctx, session, write=False)
    views = []
    for provider in PROVIDERS:
        row = await _load(session, ctx.org_id, provider)
        try:
            state = _state_from_row(row, provider)
        except HTTPException:
            state = ConnectorState(
                provider=provider,
                base_url=row.base_url if row else DEFAULTS[provider],
                secret="",
                status="error",
                detail="Saved credential could not be decrypted. Replace it.",
            )
        views.append(public_view(provider, state))
    return views


@router.post("/ollabridge/pair")
async def pair_ollabridge(
    body: PairBody,
    request: Request,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    actor = await _authorize(request, ctx, session, write=True)
    try:
        code = normalize_pairing_code(body.code)
        ensure_encryption_configured()
    except ConnectorError as exc:
        raise _http_error(exc) from exc
    user_key = f"{ctx.org_id}:{actor}"
    try:
        with pairing_submission(user_key):
            if not rate_limit("ollabridge-pair", user_key, _PAIR_LIMIT, _PAIR_WINDOW):
                raise ConnectorError(429, "Too many pairing attempts. Try again later.")
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(20.0, connect=8.0),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    remote = await client.post(CLOUD_PAIR_URL, json=pairing_request_body(code))
            except httpx.RequestError as exc:
                raise ConnectorError(502, "OllaBridge Cloud is unavailable. Try again.") from exc
            try:
                payload = remote.json()
            except ValueError:
                payload = None
            token = interpret_pairing_response(remote.status_code, payload)
            probe = probe_provider("ollabridge", CLOUD_API_BASE, token)
    except ConnectorError as exc:
        raise _http_error(exc) from exc
    row = await _load(session, ctx.org_id, "ollabridge")
    if row is None:
        row = await _blank(session, ctx.org_id, "ollabridge")
    previous = _state_from_row(row, "ollabridge")
    state = apply_probe(
        previous,
        provider="ollabridge",
        base_url=CLOUD_API_BASE,
        secret=token,
        auth_method="pair",
        probe=probe,
    )
    _write_row(row, state)
    await _audit(
        session,
        org_id=ctx.org_id,
        actor=actor,
        action="connector.pair",
        provider="ollabridge",
        status=state.status,
        request=request,
    )
    await session.commit()
    logger.info("ollabridge pairing stored org=%s status=%s", ctx.org_id, state.status)
    return response_payload(state, probe, pairing="paired")


@router.post("/{provider}")
async def save_connection(
    provider: str,
    body: SaveConnectionBody,
    request: Request,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    actor = await _authorize(request, ctx, session, write=True)
    row = await _load(session, ctx.org_id, provider)
    previous = _state_from_row(row, provider)
    try:
        base_url = validate_service_url(
            body.base_url or (previous.base_url if previous else "") or DEFAULTS[provider]
        )
        secret = merged_secret(previous.secret if previous else "", body.api_key)
        if body.api_key and body.api_key.strip():
            ensure_encryption_configured()
        probe = probe_provider(provider, base_url, secret)
    except ConnectorError as exc:
        raise _http_error(exc) from exc
    if row is None:
        row = await _blank(session, ctx.org_id, provider)
    method = "key" if secret else None
    state = apply_probe(
        previous,
        provider=provider,
        base_url=base_url,
        secret=secret,
        auth_method=method,
        probe=probe,
    )
    _write_row(row, state)
    await _audit(
        session,
        org_id=ctx.org_id,
        actor=actor,
        action="connector.save",
        provider=provider,
        status=state.status,
        request=request,
    )
    await session.commit()
    return response_payload(state, probe)


@router.post("/{provider}/test")
async def test_connection(
    provider: str,
    request: Request,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    actor = await _authorize(request, ctx, session, write=True)
    row = await _load(session, ctx.org_id, provider)
    previous = _state_from_row(row, provider)
    base_url = previous.base_url if previous and previous.base_url else DEFAULTS[provider]
    secret = previous.secret if previous else ""
    try:
        base_url = validate_service_url(base_url)
        probe = probe_provider(provider, base_url, secret)
    except ConnectorError as exc:
        raise _http_error(exc) from exc
    if row is None:
        row = await _blank(session, ctx.org_id, provider)
    state = apply_probe(
        previous,
        provider=provider,
        base_url=base_url,
        secret=secret,
        auth_method=previous.auth_method if previous else None,
        probe=probe,
    )
    _write_row(row, state)
    await _audit(
        session,
        org_id=ctx.org_id,
        actor=actor,
        action="connector.test",
        provider=provider,
        status=state.status,
        request=request,
    )
    await session.commit()
    return response_payload(state, probe)


@router.delete("/{provider}", status_code=204)
async def disconnect_connection(
    provider: str,
    request: Request,
    ctx: CtxDep,
    session: SessionDep,
) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    actor = await _authorize(request, ctx, session, write=True)
    row = await _load(session, ctx.org_id, provider)
    previous = _state_from_row(row, provider)
    state = apply_disconnect(previous, provider)
    if row is None:
        row = await _blank(session, ctx.org_id, provider)
    _write_row(row, state)
    await _audit(
        session,
        org_id=ctx.org_id,
        actor=actor,
        action="connector.disconnect",
        provider=provider,
        status="disconnected",
        request=request,
    )
    await session.commit()


def saved_for_org(provider: str, org_id: str) -> ConnectorState | None:
    """Synchronous lookup used by workers that already know the organization."""
    return load_saved_connector(provider, org_id)
