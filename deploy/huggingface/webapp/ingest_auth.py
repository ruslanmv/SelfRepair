"""Machine-client + admin authenticator for the control-plane intake API.

A request is authorized if EITHER:
  * it carries ``Authorization: Bearer <token>`` matching a configured ingest
    token -> resolved to (mapped client_id, "service"); or
  * a logged-in console session user exists -> (user.email or
    "console:"+username, "user").

Otherwise a 401 is raised.

Env:
  * SELFREPAIR_INGEST_TOKEN   - single shared secret.
  * SELFREPAIR_INGEST_CLIENT  - client_id for that secret (default
                                 "matrix-maintainer").
  * SELFREPAIR_INGEST_TOKENS  - JSON object {token: client_id} for multiple
                                 clients (merged with the single-token form).
"""
from __future__ import annotations

import json
import logging
import os

from fastapi import HTTPException, Request

from .database import SessionLocal, User

logger = logging.getLogger(__name__)


def _token_map() -> dict[str, str]:
    """Build {token: client_id}. Never logs token values."""
    mapping: dict[str, str] = {}
    single = os.environ.get("SELFREPAIR_INGEST_TOKEN", "").strip()
    if single:
        client = os.environ.get("SELFREPAIR_INGEST_CLIENT", "matrix-maintainer").strip() or "matrix-maintainer"
        mapping[single] = client
    multi = os.environ.get("SELFREPAIR_INGEST_TOKENS", "").strip()
    if multi:
        try:
            data = json.loads(multi)
            if isinstance(data, dict):
                for tok, cid in data.items():
                    if isinstance(tok, str) and tok.strip():
                        mapping[tok.strip()] = str(cid or "client")
        except Exception:
            logger.warning("SELFREPAIR_INGEST_TOKENS is not valid JSON; ignoring it.")
    return mapping


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def resolve_client(request: Request) -> tuple[str, str]:
    """Return (client_id, kind) where kind is "service" or "user".

    Raises HTTPException(401) when neither a valid ingest token nor a logged-in
    session is present.
    """
    token = _bearer(request)
    if token:
        mapping = _token_map()
        client_id = mapping.get(token)
        if client_id:
            return client_id, "service"
        # A bearer token was supplied but did not match -> reject explicitly.
        raise HTTPException(status_code=401, detail="Invalid ingest token")

    user_id = request.session.get("user_id")
    if user_id:
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(id=user_id, is_active=True).first()
            if user:
                client_id = user.email or f"console:{user.username}"
                return client_id, "user"
        finally:
            db.close()

    raise HTTPException(status_code=401, detail="Not authenticated")
