"""Live connection probes for the SelfRepair Connections page.

Each provider gets a tolerant probe that tries a few candidate endpoints and
reports the first success, so it works against both the wave-1 generic gateway
contracts and the currently deployed Spaces.

No HF_TOKEN is ever used here — SelfRepair talks to models only through the
OllaBridge gateway using an ``ob_*`` key, and to GitPilot/MatrixLab over HTTP.
"""
from __future__ import annotations

from typing import Any

import httpx

from .connector_service import DEFAULTS as _SHARED_DEFAULTS

# Same catalogue as the full API. OllaBridge defaults to Cloud, not a Space.
DEFAULTS: dict[str, str] = dict(_SHARED_DEFAULTS)

PROVIDERS = ("ollabridge", "gitpilot", "matrixlab")
PROVIDER_LABELS = {
    "ollabridge": "OllaBridge Cloud",
    "gitpilot": "GitPilot",
    "matrixlab": "MatrixLab",
}

_TIMEOUT = httpx.Timeout(25.0, connect=12.0)


def _result(status: str, detail: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": status, "detail": detail, "extra": extra or {}}


def test_ollabridge(base_url: str, api_key: str) -> dict[str, Any]:
    """Authorized model listing. A health response alone is not success."""
    from .connector_service import ConnectorError, probe_ollabridge

    try:
        return probe_ollabridge(base_url, api_key)
    except ConnectorError as exc:
        return _result("error", exc.detail, {})


def test_gitpilot(url: str, token: str) -> dict[str, Any]:
    """Health check only. This does not submit a repair."""
    from .connector_service import ConnectorError, probe_gitpilot

    try:
        return probe_gitpilot(url, token)
    except ConnectorError as exc:
        return _result("error", exc.detail, {})


def test_matrixlab(url: str, token: str) -> dict[str, Any]:
    """Capabilities and health. This does not execute a patch."""
    from .connector_service import ConnectorError, probe_matrixlab

    try:
        return probe_matrixlab(url, token)
    except ConnectorError as exc:
        return _result("error", exc.detail, {})


def test_provider(provider: str, base_url: str, secret: str) -> dict[str, Any]:
    if provider == "ollabridge":
        return test_ollabridge(base_url, secret)
    if provider == "gitpilot":
        return test_gitpilot(base_url, secret)
    if provider == "matrixlab":
        return test_matrixlab(base_url, secret)
    return _result("error", f"Unknown provider '{provider}'.", {})


def ollabridge_sample_completion(base_url: str, api_key: str, prompt: str) -> dict[str, Any]:
    """Run one tiny chat completion to prove the gateway end-to-end."""
    base = (base_url or DEFAULTS["ollabridge"]).rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"model": "code-coder", "messages": [{"role": "user", "content": prompt}]}
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
            r = c.post(f"{base}/chat/completions", headers=headers, json=payload)
        if 200 <= r.status_code < 300:
            data = r.json()
            content = (
                data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if isinstance(data, dict)
                else ""
            )
            return _result("ok", "Completion succeeded.", {"content": content[:1200]})
        return _result("error", f"Completion failed (HTTP {r.status_code}).", {"body": r.text[:400]})
    except httpx.HTTPError as e:
        return _result("error", f"Completion request failed. ({e})", {})
