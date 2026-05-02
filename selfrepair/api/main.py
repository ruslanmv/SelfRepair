"""FastAPI app factory.

The app holds an Arq pool in `app.state.queue` so route handlers can enqueue
work without re-establishing a Redis connection per request.

If Redis is unavailable at startup we DO NOT crash. The pool is set to None
and a warning is logged; routes that need the queue return 503 at request
time. This keeps the API self-test (`/healthz`) responsive during local
dev when the operator hasn't run `make start-deps` yet.
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI

from selfrepair.api.routes import (
    ci,
    health,
    issues,
    jobs,
    metrics,
    webhooks,
    webhooks_gitlab,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis_url = os.getenv("SELFREPAIR_REDIS_URL", "redis://localhost:6379/0")
    app.state.queue = None
    try:
        app.state.queue = await create_pool(RedisSettings.from_dsn(redis_url))
    except Exception:
        logger.warning(
            "redis unavailable at %s; queue features disabled. "
            "Bring deps up with `make start-deps` (Postgres + Redis).",
            redis_url,
            exc_info=True,
        )
    try:
        yield
    finally:
        if app.state.queue is not None:
            try:
                await app.state.queue.close()
            except Exception:
                logger.warning("error closing queue", exc_info=True)


def build_app() -> FastAPI:
    app = FastAPI(
        title="SelfRepair",
        version="1.0.0",
        description=(
            "AI Secure Delivery Copilot. Repository health scanning, safe "
            "AI-assisted repair, validation, and audit-ready reporting."
        ),
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(webhooks_gitlab.router)
    app.include_router(jobs.router)
    app.include_router(metrics.router)
    app.include_router(ci.router)
    app.include_router(issues.router)
    return app


app = build_app()
