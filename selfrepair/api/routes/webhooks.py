"""GitHub webhook ingestion.

Flow:
  1. Verify HMAC signature against the raw body.
  2. Enqueue an `ingest_webhook` task on Arq.
  3. Return 200 quickly so GitHub doesn't time out (it has a 10s SLA).

The heavy lifting (translating push events into jobs, running discovery on
installation events, classifying CI failures) happens in the worker, not
in the request handler.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request, status

from selfrepair.auth import verify_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Additive: the original four events, the four CI Guardian events, and
# the two Issue Watch events (issues + issue_comment). Order only matters
# for readability; the set is unordered.
_HANDLED_EVENTS = frozenset(
    {
        # Inventory / repo lifecycle
        "push",
        "pull_request",
        "installation",
        "installation_repositories",
        # CI Guardian
        "workflow_run",
        "workflow_job",
        "check_run",
        "check_suite",
        # Issue Watch
        "issues",
        "issue_comment",
    }
)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_github_delivery: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    body = await request.body()

    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        logger.error("GITHUB_WEBHOOK_SECRET is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="webhook secret not configured",
        )

    if not verify_webhook_signature(
        secret=secret, payload=body, header=x_hub_signature_256
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bad signature",
        )

    if x_github_event == "ping":
        return {"status": "pong"}

    if x_github_event not in _HANDLED_EVENTS:
        return {"status": "ignored", "event": x_github_event}

    payload = await request.json()
    queue = getattr(request.app.state, "queue", None)
    if queue is None:
        # Redis unavailable; the lifespan logged a warning at startup.
        # Surface a 503 so GitHub retries the delivery rather than the
        # caller seeing a generic 500.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="queue unavailable; bring up Redis (`make start-deps`)",
        )
    await queue.enqueue_job(
        "ingest_webhook",
        x_github_event,
        x_github_delivery,
        payload,
    )
    logger.info(
        "queued webhook event=%s delivery=%s", x_github_event, x_github_delivery
    )
    return {"status": "queued", "delivery_id": x_github_delivery}
