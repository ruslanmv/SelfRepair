"""JSON-RPC 2.0 router for the SelfRepair stable client contract.

Exposes `POST /v1/rpc` (four methods) and `GET /v1/about`. See
`docs/design/v1-rpc-contract.md` and the matrix-maintainer side
(`agent-matrix/matrix-maintainer:docs/design/selfrepair-client-contract.md`)
for the full contract.

Error envelopes follow JSON-RPC 2.0:
  -32600  invalid request
  -32601  method not found
  -32602  invalid params
  -32603  internal error
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from selfrepair import __version__ as _selfrepair_version
from selfrepair.api.v1 import engines as v1_engines
from selfrepair.api.v1.dtos import SCHEMA_VERSION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["v1-rpc"])

# JSON-RPC 2.0 error codes
_ERR_PARSE = -32700
_ERR_INVALID_REQUEST = -32600
_ERR_METHOD_NOT_FOUND = -32601
_ERR_INVALID_PARAMS = -32602
_ERR_INTERNAL = -32603

# Auth env var. If unset, requests are allowed (local-dev mode); a warning is
# logged once at module import.
_API_KEY_ENV = "SELFREPAIR_API_KEY"
if not os.getenv(_API_KEY_ENV):
    logger.warning(
        "%s is not set; /v1/rpc is running UNAUTHENTICATED (local dev mode). "
        "Set %s to require Bearer auth.",
        _API_KEY_ENV, _API_KEY_ENV,
    )


def _rpc_error(req_id: Any, code: int, message: str,
               data: Any | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _rpc_result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _check_auth(authorization: str | None) -> tuple[bool, str | None]:
    """Returns (ok, reason). When env unset, always ok."""
    expected = os.getenv(_API_KEY_ENV)
    if not expected:
        return True, None
    if not authorization:
        return False, "missing_authorization"
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False, "malformed_authorization"
    if parts[1].strip() != expected:
        return False, "bad_token"
    return True, None


# ---------------------------------------------------------------------------
# method dispatchers
# ---------------------------------------------------------------------------


class _ParamError(Exception):
    """Raised by dispatchers on invalid params (mapped to -32602)."""


def _method_scan(params: dict[str, Any]) -> dict[str, Any]:
    repo = params.get("repo")
    if not isinstance(repo, str) or not repo:
        raise _ParamError("'repo' must be a non-empty string")
    profile = params.get("profile")
    if profile is not None and not isinstance(profile, str):
        raise _ParamError("'profile' must be a string or null")
    platform = params.get("platform", "github")
    clone_url = params.get("clone_url")
    dto = v1_engines.scan_repo(repo, profile=profile, platform=platform,
                               clone_url=clone_url)
    return dto.model_dump(mode="json")


def _method_repair(params: dict[str, Any]) -> dict[str, Any]:
    repo = params.get("repo")
    if not isinstance(repo, str) or not repo:
        raise _ParamError("'repo' must be a non-empty string")
    issues = params.get("issues", [])
    if not isinstance(issues, list):
        raise _ParamError("'issues' must be a list")
    safe_only = params.get("safe_only", True)
    if not isinstance(safe_only, bool):
        raise _ParamError("'safe_only' must be a boolean")
    branch = params.get("branch")
    if branch is not None and not isinstance(branch, str):
        raise _ParamError("'branch' must be a string or null")
    platform = params.get("platform", "github")
    clone_url = params.get("clone_url")
    dto = v1_engines.heal_repo(repo, issues=issues, safe_only=safe_only,
                               branch=branch, platform=platform,
                               clone_url=clone_url)
    return dto.model_dump(mode="json")


def _method_validate(params: dict[str, Any]) -> dict[str, Any]:
    repo = params.get("repo")
    if not isinstance(repo, str) or not repo:
        raise _ParamError("'repo' must be a non-empty string")
    in_sandbox = params.get("in_sandbox", True)
    if not isinstance(in_sandbox, bool):
        raise _ParamError("'in_sandbox' must be a boolean")
    platform = params.get("platform", "github")
    clone_url = params.get("clone_url")
    dto = v1_engines.validate_repo(repo, in_sandbox=in_sandbox,
                                   platform=platform, clone_url=clone_url)
    return dto.model_dump(mode="json")


def _method_report(params: dict[str, Any]) -> dict[str, Any]:
    repo = params.get("repo")
    if not isinstance(repo, str) or not repo:
        raise _ParamError("'repo' must be a non-empty string")
    platform = params.get("platform", "github")
    clone_url = params.get("clone_url")
    dto = v1_engines.build_json_report(repo, platform=platform,
                                       clone_url=clone_url)
    return dto.model_dump(mode="json")


_METHODS = {
    "selfrepair.scan": _method_scan,
    "selfrepair.repair": _method_repair,
    "selfrepair.validate": _method_validate,
    "selfrepair.report": _method_report,
}


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@router.get("/about")
def about() -> dict[str, Any]:
    return {
        "schema_versions": [SCHEMA_VERSION],
        "service": "selfrepair",
        "version": _selfrepair_version,
    }


@router.post("/rpc")
async def rpc(request: Request,
              authorization: str | None = Header(default=None)) -> JSONResponse:
    ok, reason = _check_auth(authorization)
    if not ok:
        # Auth is a transport concern; per JSON-RPC we still return a 200 with
        # an error envelope so the client gets a structured message. Use HTTP
        # 401 for unauthenticated requests so middleware/proxies can react.
        return JSONResponse(
            status_code=401,
            content=_rpc_error(None, _ERR_INVALID_REQUEST,
                               f"unauthorized: {reason}"),
        )

    try:
        raw = await request.body()
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        return JSONResponse(
            status_code=200,
            content=_rpc_error(None, _ERR_PARSE,
                               f"parse error: {exc}"),
        )

    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=200,
            content=_rpc_error(None, _ERR_INVALID_REQUEST,
                               "request must be a JSON object"),
        )

    req_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return JSONResponse(
            status_code=200,
            content=_rpc_error(req_id, _ERR_INVALID_REQUEST,
                               "missing or invalid 'jsonrpc' (must be '2.0')"),
        )

    method = payload.get("method")
    if not isinstance(method, str):
        return JSONResponse(
            status_code=200,
            content=_rpc_error(req_id, _ERR_INVALID_REQUEST,
                               "'method' must be a string"),
        )

    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return JSONResponse(
            status_code=200,
            content=_rpc_error(req_id, _ERR_INVALID_PARAMS,
                               "'params' must be a JSON object"),
        )

    handler = _METHODS.get(method)
    if handler is None:
        return JSONResponse(
            status_code=200,
            content=_rpc_error(req_id, _ERR_METHOD_NOT_FOUND,
                               f"unknown method: {method}"),
        )

    try:
        result = handler(params)
    except _ParamError as exc:
        return JSONResponse(
            status_code=200,
            content=_rpc_error(req_id, _ERR_INVALID_PARAMS, str(exc)),
        )
    except ValidationError as exc:
        return JSONResponse(
            status_code=200,
            content=_rpc_error(req_id, _ERR_INVALID_PARAMS,
                               "validation error", data=exc.errors()),
        )
    except Exception as exc:  # noqa: BLE001 — JSON-RPC catch-all
        logger.exception("/v1/rpc internal error in %s", method)
        return JSONResponse(
            status_code=200,
            content=_rpc_error(req_id, _ERR_INTERNAL,
                               f"internal error: {exc}"),
        )

    return JSONResponse(status_code=200, content=_rpc_result(req_id, result))
