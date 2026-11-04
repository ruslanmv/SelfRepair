"""Resolve the connector a repair or validation call should use.

Saved organization credentials win when a row exists. Environment variables
are the fallback when nothing has been saved. A disconnected saved row does
not silently revive an environment token.

Secrets stay in process memory for the call. They are not logged.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from selfrepair.connectors.service import (
    DEFAULTS,
    ConnectorError,
    ConnectorState,
    assert_public_resolution,
    decrypt,
    validate_service_url,
)

logger = logging.getLogger(__name__)

Loader = Callable[[str, str], ConnectorState | None]


@dataclass(frozen=True)
class ResolvedService:
    provider: str
    base_url: str
    token: str | None
    source: str
    detail: str = ""

    @property
    def configured(self) -> bool:
        return self.source in {"saved", "environment"} and bool(self.base_url)


def _env_url(provider: str) -> str | None:
    if provider == "ollabridge":
        return os.environ.get("OLLABRIDGE_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    if provider == "gitpilot":
        return os.environ.get("SELFREPAIR_GITPILOT_URL") or os.environ.get("GITPILOT_URL")
    if provider == "matrixlab":
        return os.environ.get("SELFREPAIR_MATRIXLAB_URL") or os.environ.get("MATRIXLAB_URL")
    return None


def _env_token(provider: str) -> str | None:
    if provider == "ollabridge":
        return os.environ.get("OLLABRIDGE_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if provider == "gitpilot":
        return (
            os.environ.get("SELFREPAIR_GITPILOT_TOKEN")
            or os.environ.get("GITPILOT_TOKEN")
            or os.environ.get("GITPILOT_API_TOKEN")
        )
    if provider == "matrixlab":
        return (
            os.environ.get("SELFREPAIR_MATRIXLAB_TOKEN")
            or os.environ.get("MATRIXLAB_TOKEN")
            or os.environ.get("MATRIXLAB_BEARER_TOKEN")
        )
    return None


def _default_url(provider: str) -> str:
    if provider == "ollabridge":
        return os.environ.get("OLLABRIDGE_BASE_URL") or "https://api.ollabridge.com/v1"
    if provider == "gitpilot":
        return "http://localhost:9000"
    if provider == "matrixlab":
        return "http://localhost:8765"
    return DEFAULTS.get(provider, "")


def _guard(url: str) -> str | None:
    """Return an error detail when the URL must not be contacted."""
    if not url:
        return "No service URL is configured."
    hostname = (urlsplit(url).hostname or "").lower()
    loopback = hostname in {"localhost", "127.0.0.1", "::1"}
    try:
        safe = validate_service_url(url)
    except ConnectorError as exc:
        if loopback:
            return None
        return exc.detail
    if loopback:
        return None
    try:
        assert_public_resolution(safe)
    except ConnectorError as exc:
        return exc.detail
    return None


def _database_url() -> str | None:
    return os.environ.get("SELFREPAIR_DATABASE_URL") or os.environ.get("DATABASE_URL")


def load_saved_connector(provider: str, org_id: str) -> ConnectorState | None:
    """Read one org-scoped row. Returns None when the database is not configured."""
    url = _database_url()
    if not url:
        return None
    try:
        org = uuid.UUID(org_id)
    except ValueError:
        return None
    sync_url = url.replace("+asyncpg", "+psycopg")
    if sync_url.startswith("postgresql://"):
        sync_url = sync_url.replace("postgresql://", "postgresql+psycopg://", 1)
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session

        from selfrepair.persistence.connector_models import ServiceConnection
    except Exception:
        logger.info("saved connector lookup unavailable for %s", provider)
        return None
    engine = create_engine(sync_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            row = session.execute(
                select(ServiceConnection).where(
                    ServiceConnection.org_id == org,
                    ServiceConnection.provider == provider,
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            try:
                secret = decrypt(row.secret_enc or "")
            except ConnectorError:
                logger.warning("connector secret could not be decrypted for %s", provider)
                secret = ""
            return ConnectorState(
                provider=row.provider,
                base_url=row.base_url or "",
                secret=secret,
                status=row.status or "unknown",
                detail=row.detail or "",
                auth_method=row.auth_method,
                last_checked_at=row.last_checked_at,
                last_attempted_at=row.last_attempted_at,
            )
    except Exception:
        logger.info("saved connector lookup failed for %s", provider)
        return None
    finally:
        engine.dispose()


def resolve_service(
    provider: str,
    *,
    org_id: str | None = None,
    loader: Loader | None = None,
) -> ResolvedService:
    """Choose the endpoint for ``provider``.

    ``loader`` overrides the database read. Tests pass one; production uses
    ``load_saved_connector``.
    """
    org = org_id or os.environ.get("SELFREPAIR_ORG_ID") or None
    saved: ConnectorState | None = None
    if org:
        reader = loader or load_saved_connector
        try:
            saved = reader(provider, org)
        except Exception:
            logger.info("connector resolver skipped saved %s", provider)
            saved = None
    if saved is not None and saved.base_url:
        problem = _guard(saved.base_url)
        if problem:
            return ResolvedService(provider, "", None, "rejected", problem)
        return ResolvedService(
            provider,
            saved.base_url.rstrip("/"),
            saved.secret or None,
            "saved",
            saved.detail or "",
        )
    env_url = _env_url(provider)
    if env_url:
        problem = _guard(env_url)
        if problem:
            return ResolvedService(provider, "", None, "rejected", problem)
        return ResolvedService(
            provider,
            env_url.rstrip("/"),
            _env_token(provider) or None,
            "environment",
        )
    fallback = _default_url(provider)
    return ResolvedService(provider, fallback, _env_token(provider) or None, "default")
