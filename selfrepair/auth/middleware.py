"""Starlette middleware that resolves a session cookie into request.state.

The middleware is fail-open: if Postgres is unreachable or the session
is invalid we simply leave `request.state.session_*` unset and let the
dependency layer fall back to the dev-org or 401-on-private routes.
This keeps `/healthz` responsive even if the DB is down.
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from selfrepair.api.deps import get_app_sessionmaker
from selfrepair.auth.cookies import COOKIE_NAME
from selfrepair.auth.sessions import lookup_session, touch_session

logger = logging.getLogger(__name__)


class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.session_user_id = None
        request.state.session_org_id = None
        request.state.session_id = None

        token = request.cookies.get(COOKIE_NAME)
        if token:
            try:
                sessionmaker = get_app_sessionmaker()
                async with sessionmaker() as db:
                    row = await lookup_session(db, token)
                    if row is not None:
                        request.state.session_user_id = row.user_id
                        request.state.session_org_id = row.org_id
                        request.state.session_id = row.id
                        await touch_session(db, row)
                        await db.commit()
            except Exception:  # pragma: no cover - middleware is fail-open
                logger.warning(
                    "session middleware failed; continuing as anonymous",
                    exc_info=True,
                )
        return await call_next(request)
