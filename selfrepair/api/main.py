"""FastAPI app factory.

Middleware stack (outermost first on requests):

1. CORSMiddleware           — preflight before anything else.
2. RequestIdMiddleware      — stamp / echo X-Request-Id for logs and audit.
3. RateLimitMiddleware      — redis-backed window on /v1/auth/login etc.
4. IdempotencyMiddleware    — cache POST/PUT/PATCH/DELETE responses by
                              Idempotency-Key + org scope.
5. SessionMiddleware        — resolve cookie session into request.state
                              before any route handler runs.

FastAPI applies middleware in reverse-add order, so the order of the
`add_middleware` calls below is the inverse of the request flow above.
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from selfrepair.api.middleware import (
    IdempotencyMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
)
from selfrepair.api.routes import (
    audit,
    auth,
    ci,
    dashboard,
    findings,
    health,
    integrations,
    issues,
    jobs,
    metrics,
    policies,
    repairs,
    repos,
    schedules,
    webhooks,
    webhooks_gitlab,
)
from selfrepair.api.v1.rpc import router as v1_rpc_router
from selfrepair.auth.middleware import SessionMiddleware

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


def _cors_origins() -> list[str]:
    raw = os.getenv("SELFREPAIR_CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:3000", "http://localhost:8080"]
    return [o.strip() for o in raw.split(",") if o.strip()]


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
    # Innermost (added first):
    app.add_middleware(SessionMiddleware)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    # Outermost (added last):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-Id",
            "X-Total-Count",
            "X-Idempotent-Replay",
        ],
    )
    # /v1/* cross-origin surface for the matrix-maintainer status site and
    # other external clients of the stable contract. Wide-open by design so
    # the status site can call directly when proxied.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(webhooks.router)
    app.include_router(webhooks_gitlab.router)
    app.include_router(repos.router)
    app.include_router(findings.router)
    app.include_router(repairs.router)
    app.include_router(jobs.router)
    app.include_router(dashboard.router)
    app.include_router(audit.router)
    app.include_router(policies.router)
    app.include_router(schedules.router)
    app.include_router(integrations.router)
    app.include_router(metrics.router)
    app.include_router(ci.router)
    app.include_router(issues.router)
    # v1 stable client contract (JSON-RPC over /v1/rpc + /v1/about)
    app.include_router(v1_rpc_router)
    return app


app = build_app()
