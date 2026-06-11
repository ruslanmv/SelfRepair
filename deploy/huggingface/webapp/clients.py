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

# Sensible defaults pointing at the live Spaces.
DEFAULTS: dict[str, str] = {
    "ollabridge": "https://ruslanmv-ollabridge.hf.space/v1",
    "gitpilot": "https://ruslanmv-gitpilot.hf.space",
    "matrixlab": "https://ruslanmv-matrixlab.hf.space",
}

PROVIDERS = ("ollabridge", "gitpilot", "matrixlab")
PROVIDER_LABELS = {
    "ollabridge": "OllaBridge Cloud",
    "gitpilot": "GitPilot",
    "matrixlab": "MatrixLab",
}

_TIMEOUT = httpx.Timeout(25.0, connect=12.0)


def _result(status: str, detail: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": status, "detail": detail, "extra": extra or {}}


def _get(url: str, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
        r = c.get(url, headers=headers or {})
        body: Any
        try:
            body = r.json()
        except Exception:
            body = r.text[:400]
        return r.status_code, body


def test_ollabridge(base_url: str, api_key: str) -> dict[str, Any]:
    """Probe OllaBridge: list models (auth) and report resolved aliases/models."""
    base = (base_url or DEFAULTS["ollabridge"]).rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    # 1) Models endpoint is the strongest signal of a working gateway.
    try:
        code, body = _get(f"{base}/models", headers=headers)
        if 200 <= code < 300:
            ids = []
            if isinstance(body, dict):
                data = body.get("data") or body.get("models") or []
                ids = [m.get("id") if isinstance(m, dict) else m for m in data]
            return _result("ok", f"Connected — {len(ids)} model(s)/alias(es) available.", {"models": ids[:24]})
        if code in (401, 403):
            return _result("error", f"Reachable but unauthorized ({code}). Check the API key.", {})
    except httpx.HTTPError as e:
        last = str(e)
    else:
        last = f"HTTP {code}"
    # 2) Fall back to the Space root health.
    root = base[:-3] if base.endswith("/v1") else base
    try:
        code, _ = _get(f"{root}/health")
        if 200 <= code < 300:
            return _result("ok", "Service reachable (health ok); /models not authorized yet.", {})
    except httpx.HTTPError as e:
        last = str(e)
    return _result("error", f"Could not reach OllaBridge /models. ({last})", {})


def test_gitpilot(url: str, token: str) -> dict[str, Any]:
    base = (url or DEFAULTS["gitpilot"]).rstrip("/")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    last = ""
    for path in ("/v1/health", "/health", "/"):
        try:
            code, body = _get(f"{base}{path}", headers=headers)
            if 200 <= code < 300:
                ver = body.get("version") if isinstance(body, dict) else None
                return _result("ok", f"GitPilot reachable at {path}" + (f" (v{ver})" if ver else "."), {})
            last = f"HTTP {code} at {path}"
        except httpx.HTTPError as e:
            last = str(e)
    return _result("error", f"Could not reach GitPilot. ({last})", {})


def test_matrixlab(url: str, token: str) -> dict[str, Any]:
    base = (url or DEFAULTS["matrixlab"]).rstrip("/")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    last = ""
    profiles: list[str] = []
    # capabilities first (richer), then health.
    for path in ("/capabilities", "/health"):
        try:
            code, body = _get(f"{base}{path}", headers=headers)
            if 200 <= code < 300:
                if isinstance(body, dict) and body.get("profiles"):
                    profiles = list(body["profiles"])
                if path == "/capabilities" and profiles:
                    return _result("ok", f"MatrixLab reachable — {len(profiles)} profile(s).", {"profiles": profiles})
                if path == "/health":
                    return _result("ok", "MatrixLab health ok.", {"profiles": profiles})
            else:
                last = f"HTTP {code} at {path}"
        except httpx.HTTPError as e:
            last = str(e)
    return _result("error", f"Could not reach MatrixLab. ({last})", {})


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
