"""API-level Starlette middleware.

Three concerns landed together because they share a single Redis
client idiom and need a stable order in `build_app()`:

* `RequestIdMiddleware` — stamp every request with a UUID4 (or echo the
  inbound `X-Request-Id`) so logs and audit rows can correlate.
* `RateLimitMiddleware` — Redis-backed fixed-window per-IP rate
  limiting on a small allowlist of mutating endpoints. Fails open if
  Redis is unreachable so a broker outage doesn't lock everyone out.
* `IdempotencyMiddleware` — honours the `Idempotency-Key` header on
  mutating methods. Caches the response body+status for 24h so a
  client can safely retry a failed POST without creating duplicate
  jobs/comments/etc.

All three are wired into `build_app()` and ordered such that CORS is
outermost (preflight first), RequestId stamps before rate limiting and
idempotency look it up, and SessionMiddleware is innermost so the
request-context dependency sees session state.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from selfrepair.api.events import aclose, make_redis_client

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-Id"
IDEMPOTENCY_HEADER = "Idempotency-Key"
_IDEM_TTL_SECONDS = 24 * 60 * 60
_IDEM_INFLIGHT_TTL_SECONDS = 600


# --------------------------- request id --------------------------------


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Echo or generate a request id; expose it on `request.state` and the
    response header.

    The id flows into structured logs (callers attach `request_id` to
    their logger context) and into audit rows so support has a single
    string to grep when diagnosing customer reports.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response


# ---------------------------- rate limit -------------------------------


@dataclass(frozen=True)
class _RateRule:
    name: str
    method: str
    path_prefix: str
    limit: int
    window_seconds: int


_RATE_RULES: tuple[_RateRule, ...] = (
    # Login is the highest-value brute force target.
    _RateRule("auth.login", "POST", "/v1/auth/login", limit=10, window_seconds=300),
    # Job creation: cap per-IP runaway loops.
    _RateRule("jobs.create", "POST", "/v1/jobs", limit=120, window_seconds=60),
    # Issue sync: provider rate limits already exist downstream; protect
    # the API too so a stuck UI button can't fan out.
    _RateRule("issues.sync", "POST", "/v1/issues/sync", limit=20, window_seconds=60),
)


def _match_rule(method: str, path: str) -> _RateRule | None:
    for rule in _RATE_RULES:
        if rule.method == method and path.startswith(rule.path_prefix):
            # Exact match for /v1/auth/login or /v1/jobs but tolerate
            # trailing slashes / sub-paths conservatively.
            if path == rule.path_prefix or path.startswith(
                rule.path_prefix + "/"
            ):
                return rule
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rule = _match_rule(request.method, request.url.path)
        if rule is None:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        bucket = int(time.time()) // rule.window_seconds
        key = f"rl:{rule.name}:{ip}:{bucket}"
        client = None
        count = 0
        try:
            client = make_redis_client()
            count = int(await client.incr(key))
            if count == 1:
                await client.expire(key, rule.window_seconds)
        except Exception:  # pragma: no cover - fail open
            logger.debug("rate-limit redis unavailable; passing through", exc_info=True)
            if client is not None:
                await aclose(client)
            return await call_next(request)
        finally:
            if client is not None:
                await aclose(client)

        if count > rule.limit:
            retry_after = rule.window_seconds - (
                int(time.time()) % rule.window_seconds
            )
            return JSONResponse(
                {"detail": "rate limit exceeded", "rule": rule.name},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)


# ---------------------------- idempotency ------------------------------


_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _idem_fingerprint(
    *, org_id: str, method: str, path: str, key: str
) -> str:
    raw = f"{method}|{path}|{org_id}|{key}".encode()
    return hashlib.sha256(raw).hexdigest()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Replays the cached response for a previously-seen Idempotency-Key.

    Skipped if:
      - the request method is not POST/PUT/PATCH/DELETE
      - the client didn't send `Idempotency-Key`
      - Redis is unreachable (we'd rather risk a duplicate than refuse
        the request)

    Stored entries hold the response status, headers, and body. The
    body is captured by exhausting the response's body iterator, so
    streaming responses (SSE) shouldn't reach this path — they're GET
    only.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)
        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key:
            return await call_next(request)

        org_id = (
            str(getattr(request.state, "session_org_id", "") or "anon")
        )
        fp = _idem_fingerprint(
            org_id=org_id,
            method=request.method,
            path=request.url.path,
            key=key,
        )
        cache_key = f"idem:{fp}"

        client = make_redis_client()
        try:
            cached = await client.get(cache_key)
            if cached:
                try:
                    payload = json.loads(cached)
                    if payload.get("ct") == "in-flight":
                        await aclose(client)
                        return JSONResponse(
                            {
                                "detail": (
                                    "a request with this Idempotency-Key "
                                    "is still in flight"
                                ),
                            },
                            status_code=409,
                        )
                    body = base64.b64decode(payload["b"])
                    headers = payload.get("h") or {}
                    headers["X-Idempotent-Replay"] = "true"
                    await aclose(client)
                    return Response(
                        content=body,
                        status_code=int(payload["s"]),
                        headers=headers,
                        media_type=payload.get("mt"),
                    )
                except Exception:  # pragma: no cover - bad cache entry
                    logger.warning(
                        "idempotency: stale cache; falling through",
                        exc_info=True,
                    )
            # Mark in-flight to debounce concurrent retries.
            await client.set(
                cache_key,
                json.dumps({"ct": "in-flight"}),
                ex=_IDEM_INFLIGHT_TTL_SECONDS,
                nx=True,
            )
        except Exception:  # pragma: no cover - fail open on Redis errors
            logger.debug(
                "idempotency redis unavailable; passing through",
                exc_info=True,
            )
            await aclose(client)
            return await call_next(request)

        try:
            response = await call_next(request)
        except Exception:
            try:
                await client.delete(cache_key)
            except Exception:
                pass
            await aclose(client)
            raise

        # Buffer body so we can both forward it and persist it.
        body_chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            body_chunks.append(
                chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
            )
        body = b"".join(body_chunks)
        try:
            stored = {
                "s": response.status_code,
                "b": base64.b64encode(body).decode("ascii"),
                "mt": response.media_type,
                "h": {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower()
                    not in {
                        "content-length",
                        "transfer-encoding",
                        "x-idempotent-replay",
                    }
                },
            }
            await client.set(
                cache_key, json.dumps(stored), ex=_IDEM_TTL_SECONDS
            )
        except Exception:  # pragma: no cover
            logger.warning(
                "idempotency: could not persist cache", exc_info=True
            )
        finally:
            await aclose(client)

        # Rebuild the response from the buffered body so it can be sent.
        new_headers = dict(response.headers)
        new_headers.pop("content-length", None)
        new_headers.pop("transfer-encoding", None)
        return Response(
            content=body,
            status_code=response.status_code,
            headers=new_headers,
            media_type=response.media_type,
        )
