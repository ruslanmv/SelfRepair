"""GitLab webhook ingestion (Issue Watch only, Phase-1).

Flow:
  1. Verify the static secret in `X-Gitlab-Token` matches the configured
     GITLAB_WEBHOOK_SECRET.
  2. Enqueue an `ingest_gitlab_webhook` task on Arq.
  3. Return 200 quickly so GitLab doesn't retry on timeout.

Why a static-token check (not HMAC like GitHub): GitLab's webhook UI only
exposes a static token; if the secret rotates, the operator updates both
sides. The check is constant-time to keep timing-attack risk negligible.

GitLab issue events use the `Issue Hook` X-Gitlab-Event value; comments
arrive as `Note Hook`. Other event types are acknowledged-and-ignored so
adding new ones doesn't crash the route.
"""
from __future__ import annotations

import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


_HANDLED_EVENTS = frozenset({"Issue Hook", "Note Hook"})


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    x_gitlab_event: str = Header(default=""),
    x_gitlab_token: str | None = Header(default=None),
) -> dict[str, str]:
    secret = os.getenv("GITLAB_WEBHOOK_SECRET")
    if not secret:
        logger.error("GITLAB_WEBHOOK_SECRET is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="webhook secret not configured",
        )

    if not x_gitlab_token or not hmac.compare_digest(secret, x_gitlab_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bad token",
        )

    if x_gitlab_event not in _HANDLED_EVENTS:
        return {"status": "ignored", "event": x_gitlab_event}

    payload = await request.json()
    queue = getattr(request.app.state, "queue", None)
    if queue is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="queue unavailable; bring up Redis (`make start-deps`)",
        )
    await queue.enqueue_job(
        "ingest_gitlab_webhook",
        x_gitlab_event,
        payload,
    )
    logger.info("queued gitlab webhook event=%s", x_gitlab_event)
    return {"status": "queued", "event": x_gitlab_event}
