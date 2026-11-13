"""Service authentication for the agent-repair API. Fails closed.

A request is accepted only when all of these hold:
  - agent repair is configured (token, secret, org, repository allow-list);
  - `Authorization: Bearer <token>` matches, compared in constant time;
  - `X-LangReplay-Timestamp` is within MAX_SKEW_SECONDS of now;
  - `X-LangReplay-Signature` is `v1=` + hex HMAC-SHA256 of `timestamp + "." + raw body`, compared in constant time.

The org is the configured one. Headers such as X-SelfRepair-Org-Id or X-SelfRepair-Actor are never read here.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from selfrepair.agent_repair import settings as cfg


def signature(secret: str, timestamp: str, body: bytes) -> str:
    return "v1=" + hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ServiceCaller:
    settings: cfg.AgentRepairSettings
    body: bytes
    ip: str | None


async def service_caller(request: Request) -> ServiceCaller:
    settings = cfg.load()
    if not settings.enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "agent repair is not enabled: set SELFREPAIR_AGENT_REPAIR_TOKEN, _SECRET, _ORG_ID and _REPOS")
    header = request.headers.get("authorization", "")
    presented = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not hmac.compare_digest(presented.encode(), settings.token.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid service token")
    timestamp = request.headers.get("x-langreplay-timestamp", "")
    try:
        skew = abs(time.time() - int(timestamp))
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-LangReplay-Timestamp") from None
    if skew > cfg.MAX_SKEW_SECONDS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "the request timestamp is too old or in the future")
    body = await request.body()
    expected = signature(settings.secret, timestamp, body)
    if not hmac.compare_digest(expected.encode(), request.headers.get("x-langreplay-signature", "").encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid request signature")
    return ServiceCaller(settings=settings, body=body, ip=request.client.host if request.client else None)
