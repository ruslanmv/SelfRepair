"""Shared connector rules for OllaBridge, GitPilot, and MatrixLab.

This module is the single implementation used by the full FastAPI backend
and the Hugging Face Space webapp. It has no dependency on either app's
database, session, or route layer.

OllaBridge pairing contract (verified against ollabridge-cloud):

* The dashboard ``POST /dashboard/start-pairing`` creates a short-lived
  user code while the user is signed in and stores that user id on the
  pairing session.
* SelfRepair exchanges the code with
  ``POST https://app.ollabridge.com/device/pair-simple``.
* Request body: ``{"code": "ABCD-1234", "label": "SelfRepair", "client": {...}}``.
* Success body: ``{"status": "ok", "device_token": "...", "device_id": "..."}``.
* Failure body: ``{"status": "error", "error": "<stable message>"}`` with HTTP 200.
* Codes that were never linked to a signed-in account, expired codes, and
  already-used codes do not return a token.
* The device token is an opaque bearer credential for ``/v1/models`` and
  ``/v1/chat/completions``. It must never be logged or returned to the browser.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import logging
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

PROVIDERS = ("ollabridge", "gitpilot", "matrixlab")
LABELS = {
    "ollabridge": "OllaBridge Cloud",
    "gitpilot": "GitPilot",
    "matrixlab": "MatrixLab",
}
DEFAULTS = {
    "ollabridge": "https://app.ollabridge.com/v1",
    "gitpilot": "https://ruslanmv-gitpilot.hf.space",
    "matrixlab": "https://ruslanmv-matrixlab.hf.space",
}
CLOUD_ORIGIN = "https://app.ollabridge.com"
CLOUD_PAIR_URL = f"{CLOUD_ORIGIN}/device/pair-simple"
CLOUD_API_BASE = f"{CLOUD_ORIGIN}/v1"

_DEV_ENVS = {"dev", "test", "local", "ci"}
_DEV_KEY = "selfrepair-dev-insecure-key-change-me"
_PROBE_TIMEOUT = httpx.Timeout(20.0, connect=8.0)
_PAIR_TIMEOUT = httpx.Timeout(20.0, connect=8.0)

_BUCKETS: dict[str, tuple[int, float]] = {}
_BUCKET_LOCK = threading.Lock()
_PAIR_LOCKS: dict[str, threading.Lock] = {}
_PAIR_LOCKS_GUARD = threading.Lock()


class ConnectorError(Exception):
    """Safe, user-facing connector failure. ``detail`` never contains a secret."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class ConnectorState:
    """In-memory connector row. ``secret`` is plaintext only inside the process."""

    provider: str
    base_url: str
    secret: str = ""
    status: str = "unknown"
    detail: str = ""
    auth_method: str | None = None
    last_checked_at: datetime | None = None
    last_attempted_at: datetime | None = None


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------


def _dev_fallback_allowed() -> bool:
    if os.environ.get("SELFREPAIR_INSECURE_COOKIES") == "1":
        return True
    return os.environ.get("SELFREPAIR_ENV", "").strip().lower() in _DEV_ENVS


def _secret_material() -> str:
    secret = os.environ.get("SELFREPAIR_SECRET_KEY") or os.environ.get("SESSION_SECRET")
    if secret:
        return secret
    if _dev_fallback_allowed():
        return _DEV_KEY
    raise ConnectorError(
        503,
        "Server encryption key is not configured. Set SELFREPAIR_SECRET_KEY.",
    )


def _fernet() -> Fernet:
    raw = base64.urlsafe_b64encode(hashlib.sha256(_secret_material().encode()).digest())
    return Fernet(raw)


def ensure_encryption_configured() -> None:
    """Raise before a new secret is written when production has no key."""
    _secret_material()


def encrypt(plaintext: str) -> str:
    """Encrypt a secret. Empty input returns an empty string."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a stored secret. Undecryptable values become an empty string."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except ConnectorError:
        raise
    except (InvalidToken, ValueError, TypeError):
        return ""


def mask(secret: str) -> str:
    """Render a secret for display without exposing it."""
    if not secret:
        return ""
    if len(secret) <= 10:
        return "••••••"
    return f"{secret[:6]}…{secret[-4:]}"


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------


def _local_http(scheme: str, hostname: str) -> bool:
    """Development may call a loopback HTTP service. HTTPS loopback stays blocked."""
    return (
        _dev_fallback_allowed()
        and scheme == "http"
        and hostname in {"localhost", "127.0.0.1", "::1"}
    )


def _blocked_ip(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _blocked_hostname(hostname: str) -> bool:
    host = hostname.strip(".").lower()
    if host in {"metadata.google.internal", "metadata.internal"}:
        return True
    if host.endswith((".local", ".internal", ".localhost")):
        return True
    if host.isdigit():
        return True
    try:
        packed = int(host)
        if 0 <= packed <= 0xFFFFFFFF:
            return True
    except ValueError:
        pass
    return _blocked_ip(host)


def validate_service_url(raw: str) -> str:
    """Accept an HTTPS service URL. Local HTTP is limited to development."""
    value = (raw or "").strip().rstrip("/")
    if not value:
        raise ConnectorError(422, "Enter the service URL.")
    parsed = urlsplit(value)
    hostname = parsed.hostname
    if (
        not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ConnectorError(
            422,
            "Enter a valid HTTPS service URL without embedded credentials.",
        )
    local_http = _local_http(parsed.scheme, hostname)
    if parsed.scheme != "https" and not local_http:
        raise ConnectorError(
            422,
            "Enter a valid HTTPS service URL (localhost HTTP is for development only).",
        )
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise ConnectorError(422, "Enter a valid HTTPS service URL.")
    if _blocked_hostname(hostname) and not local_http:
        raise ConnectorError(
            422,
            "That URL points at a private or local network address and cannot be used.",
        )
    return value


def assert_public_resolution(url: str) -> None:
    """Refuse a hostname that resolves to a non-public address.

    Called immediately before an outbound probe. Resolution failure is left
    to the HTTP client; a positive private answer is rejected.
    """
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if _local_http(parsed.scheme, hostname):
        return
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return
    for info in infos:
        address = info[4][0]
        if _blocked_ip(address):
            raise ConnectorError(
                422,
                "That hostname resolves to a private network address and was not contacted.",
            )


def assert_mutation_origin(
    headers: Mapping[str, str],
    *,
    host: str,
    extra_origins: set[str] | None = None,
) -> None:
    """Block cross-site cookie mutations.

    A missing Origin is allowed so non-browser clients and tests keep working.
    Browsers send Origin on cross-site POSTs. SameSite=None cookies (required
    for the Hugging Face iframe) would otherwise accept those requests.
    """
    fetch_site = (headers.get("sec-fetch-site") or headers.get("Sec-Fetch-Site") or "").lower()
    if fetch_site == "cross-site":
        raise ConnectorError(403, "Cross-site request blocked.")
    origin = headers.get("origin") or headers.get("Origin") or ""
    if not origin:
        return
    allowed_hosts = {host.lower()}
    if ":" not in host:
        allowed_hosts.add(f"{host}:443".lower())
    allowed = {f"https://{item}" for item in allowed_hosts}
    allowed.add(f"http://{host}".lower())
    for item in extra_origins or set():
        allowed.add(item.rstrip("/").lower())
    raw = os.environ.get("SELFREPAIR_CSRF_ORIGINS", "")
    for item in raw.split(","):
        if item.strip():
            allowed.add(item.strip().rstrip("/").lower())
    if origin.rstrip("/").lower() not in allowed:
        raise ConnectorError(403, "This request origin is not allowed.")


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------


def _platform_name() -> str:
    plat = sys.platform
    if plat.startswith("linux"):
        return "linux"
    if plat == "darwin":
        return "macos"
    if plat.startswith("win"):
        return "windows"
    return "other"


def normalize_pairing_code(raw: Any) -> str:
    """Accept ``ABCD-1234`` or ``ABCD1234`` and return the dashed form."""
    if not isinstance(raw, str):
        raise ConnectorError(422, "Enter the 8-character OllaBridge pairing code.")
    compact = "".join(ch for ch in raw.strip().upper() if ch.isalnum())
    if len(compact) != 8 or not compact.isalnum():
        raise ConnectorError(422, "Enter the 8-character OllaBridge pairing code.")
    return f"{compact[:4]}-{compact[4:]}"


def pairing_request_body(code: str) -> dict[str, Any]:
    """Body for ``POST /device/pair-simple``. The code is the only secret."""
    return {
        "code": code,
        "label": "SelfRepair",
        "client": {
            "name": "SelfRepair",
            "vendor": "ruslanmv",
            "platform": _platform_name(),
        },
    }


def interpret_pairing_response(status_code: int, payload: Any) -> str:
    """Return the device token or raise a safe error. Never echoes the token."""
    if status_code == 429:
        raise ConnectorError(429, "OllaBridge pairing is rate-limited. Try later.")
    if not isinstance(payload, dict):
        raise ConnectorError(
            422,
            "Pairing failed. Check the code or generate a new one in OllaBridge.",
        )
    error = payload.get("error") if isinstance(payload.get("error"), str) else ""
    lowered = error.lower()
    if "expired" in lowered:
        raise ConnectorError(
            422,
            "That pairing code has expired. Generate a new code in OllaBridge Cloud.",
        )
    if "already used" in lowered or "already claimed" in lowered:
        raise ConnectorError(
            422,
            "That pairing code was already used. Generate a new code in OllaBridge Cloud.",
        )
    if "not linked" in lowered or "authenticated account" in lowered:
        raise ConnectorError(
            422,
            "Sign in to OllaBridge Cloud and generate the code there, then paste it here. "
            "Codes that are not linked to your account cannot be paired.",
        )
    if "invalid" in lowered:
        raise ConnectorError(
            422,
            "That pairing code was not recognized. Generate a new code in OllaBridge Cloud.",
        )
    token = payload.get("device_token")
    if (
        status_code != 200
        or payload.get("status") != "ok"
        or not isinstance(token, str)
        or not token
    ):
        raise ConnectorError(
            422,
            "Pairing failed. Check the code or generate a new one in OllaBridge.",
        )
    return token


def rate_limit(action: str, identifier: str, limit: int, window_seconds: int) -> bool:
    """Process-local fixed window. Returns True when the attempt is allowed.

    This limiter does not fail open. Production deployments should also count
    in Redis; a Redis outage must not disable this local cap.
    """
    now = time.monotonic()
    key = f"{action}:{identifier}"
    with _BUCKET_LOCK:
        count, expires = _BUCKETS.get(key, (0, 0.0))
        if expires <= now:
            _BUCKETS[key] = (1, now + window_seconds)
            return True
        count += 1
        _BUCKETS[key] = (count, expires)
        return count <= limit


def reset_rate_limits() -> None:
    """Test helper."""
    with _BUCKET_LOCK:
        _BUCKETS.clear()


class pairing_submission:
    """Reject overlapping pairing attempts for the same user."""

    def __init__(self, user_key: str) -> None:
        self.user_key = user_key
        self._lock: threading.Lock | None = None

    def __enter__(self) -> pairing_submission:
        with _PAIR_LOCKS_GUARD:
            lock = _PAIR_LOCKS.setdefault(self.user_key, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ConnectorError(429, "A pairing attempt is already in progress.")
        self._lock = lock
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._lock is not None:
            self._lock.release()


# ---------------------------------------------------------------------------
# Probes — connectivity is not a completed repair or sandbox run
# ---------------------------------------------------------------------------


def _result(
    status: str,
    detail: str,
    extra: dict[str, Any] | None = None,
    *,
    access_verified: bool = False,
) -> dict[str, Any]:
    return {
        "status": status,
        "detail": detail,
        "extra": extra or {},
        "access_verified": access_verified,
        # Settings checks never execute a repair plan or a sandbox job.
        "workflow_verified": False,
    }


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, Any]:
    assert_public_resolution(url)
    with httpx.Client(
        timeout=_PROBE_TIMEOUT,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get(url, headers=headers)
    if 300 <= response.status_code < 400:
        raise ConnectorError(502, "The service redirected the check. Redirects are not followed.")
    try:
        body: Any = response.json()
    except ValueError:
        body = (response.text or "")[:400]
    return response.status_code, body


def probe_ollabridge(
    base_url: str,
    api_key: str,
    *,
    getter: Callable[[str, dict[str, str]], tuple[int, Any]] | None = None,
) -> dict[str, Any]:
    """Authorized ``GET /v1/models`` is access verification, not a repair run."""
    base = validate_service_url(base_url or DEFAULTS["ollabridge"])
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    get = getter or _http_get
    last = "no response"
    try:
        code, body = get(f"{base}/models", headers)
        if 200 <= code < 300 and api_key:
            ids: list[Any] = []
            if isinstance(body, dict):
                data = body.get("data") or body.get("models") or []
                if isinstance(data, list):
                    ids = [item.get("id") if isinstance(item, dict) else item for item in data]
            return _result(
                "ok",
                f"Authorized model access confirmed — {len(ids)} model(s) listed. "
                "This check did not run a repair completion.",
                {"models": [str(item) for item in ids[:24] if item]},
                access_verified=True,
            )
        if 200 <= code < 300:
            return _result(
                "reachable",
                "The gateway answered without a credential. Model access is not verified.",
            )
        if code in (401, 403):
            return _result(
                "error",
                "OllaBridge rejected the credential. Pair again or replace the API key."
                if api_key
                else "OllaBridge requires a device token or API key.",
            )
        last = f"HTTP {code}"
    except ConnectorError as exc:
        return _result("error", exc.detail)
    except httpx.HTTPError:
        last = "network error"
    root = base[:-3] if base.endswith("/v1") else base
    try:
        code, _body = get(f"{root}/health", {})
        if 200 <= code < 300:
            return _result(
                "reachable",
                "Gateway reachable, but model access is not verified. "
                "Pair a device or provide a valid API key.",
            )
    except (ConnectorError, httpx.HTTPError):
        pass
    return _result("error", f"Could not verify OllaBridge model access. ({last})")


def probe_gitpilot(
    url: str,
    token: str,
    *,
    getter: Callable[[str, dict[str, str]], tuple[int, Any]] | None = None,
) -> dict[str, Any]:
    """Health only. A 200 response is not a completed repair."""
    base = validate_service_url(url or DEFAULTS["gitpilot"])
    get = getter or _http_get
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    last = "no response"
    saw_unauthorized = False
    for path in ("/health", "/v1/health", "/"):
        try:
            code, body = get(f"{base}{path}", headers)
        except ConnectorError as exc:
            return _result("error", exc.detail)
        except httpx.HTTPError:
            last = "network error"
            continue
        if code in (401, 403):
            saw_unauthorized = True
            last = f"HTTP {code} at {path}"
            continue
        if 200 <= code < 300:
            version = body.get("version") if isinstance(body, dict) else None
            if token and not saw_unauthorized:
                # The health route may ignore credentials. Say so.
                detail = (
                    "GitPilot responded to a health check. "
                    "A repair was not submitted, so this is not end-to-end verification."
                )
                status = "reachable"
                access = False
            elif token:
                detail = (
                    "GitPilot accepted the access token on a health check. "
                    "A repair was not submitted."
                )
                status = "ok"
                access = True
            else:
                detail = (
                    "GitPilot is reachable. No access token is saved, and no repair was submitted."
                )
                status = "reachable"
                access = False
            extra = {"version": version} if version else {}
            return _result(status, detail, extra, access_verified=access)
        last = f"HTTP {code} at {path}"
    if saw_unauthorized:
        return _result("error", "GitPilot rejected the access token.")
    return _result("error", f"Could not reach GitPilot. ({last})")


def probe_matrixlab(
    url: str,
    token: str,
    *,
    getter: Callable[[str, dict[str, str]], tuple[int, Any]] | None = None,
) -> dict[str, Any]:
    """Capabilities and health. Neither executes a patch."""
    base = validate_service_url(url or DEFAULTS["matrixlab"])
    get = getter or _http_get
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    last = "no response"
    profiles: list[str] = []
    unauthorized = False
    for path in ("/capabilities", "/health", "/profiles"):
        try:
            code, body = get(f"{base}{path}", headers)
        except ConnectorError as exc:
            return _result("error", exc.detail)
        except httpx.HTTPError:
            last = "network error"
            continue
        if code in (401, 403):
            unauthorized = True
            last = f"HTTP {code} at {path}"
            continue
        if 200 <= code < 300 and isinstance(body, dict):
            found = body.get("profiles")
            if isinstance(found, list):
                profiles = [str(item) for item in found if isinstance(item, (str, int))]
            elif isinstance(found, dict):
                profiles = [str(item) for item in found.keys()]
        if 200 <= code < 300 and path == "/capabilities" and profiles:
            return _result(
                "reachable",
                f"MatrixLab reported {len(profiles)} validation profile(s). "
                "A patch was not executed in the sandbox.",
                {"profiles": profiles},
            )
        if 200 <= code < 300 and path == "/health":
            extra = {"profiles": profiles} if profiles else {}
            return _result(
                "reachable",
                "MatrixLab health check succeeded. A patch was not executed in the sandbox.",
                extra,
            )
        if 200 <= code < 300 and profiles:
            return _result(
                "reachable",
                f"MatrixLab reported {len(profiles)} validation profile(s). "
                "A patch was not executed in the sandbox.",
                {"profiles": profiles},
            )
        if not (200 <= code < 300):
            last = f"HTTP {code} at {path}"
    if unauthorized:
        return _result("error", "MatrixLab rejected the access token.")
    return _result("error", f"Could not reach MatrixLab. ({last})")


def probe_provider(
    provider: str,
    base_url: str,
    secret: str,
    *,
    getter: Callable[[str, dict[str, str]], tuple[int, Any]] | None = None,
) -> dict[str, Any]:
    if provider == "ollabridge":
        return probe_ollabridge(base_url, secret, getter=getter)
    if provider == "gitpilot":
        return probe_gitpilot(base_url, secret, getter=getter)
    if provider == "matrixlab":
        return probe_matrixlab(base_url, secret, getter=getter)
    raise ConnectorError(404, "Unknown provider.")


# ---------------------------------------------------------------------------
# State transitions and public views
# ---------------------------------------------------------------------------


def display_status(state: ConnectorState | None) -> str:
    """Human status. Only values supported by a stored check are returned."""
    if state is None or (state.status in {"", "unknown"} and not state.secret and not state.last_attempted_at):
        return "Not configured"
    status = state.status or "unknown"
    if status == "disconnected":
        return "Disconnected"
    if status == "expired":
        return "Expired"
    if status == "pairing":
        return "Pairing"
    if status == "error":
        return "Needs attention"
    if status == "ok":
        return "Connected" if state.secret else "Reachable"
    if status == "reachable":
        return "Reachable"
    if state.secret:
        return "Not verified"
    return "Not configured"


def public_view(provider: str, state: ConnectorState | None) -> dict[str, Any]:
    """JSON view for the SPA. The secret itself is never included."""
    secret = state.secret if state else ""
    base = (state.base_url if state and state.base_url else DEFAULTS.get(provider, ""))
    probe_status = state.status if state else "unknown"
    access_verified = probe_status == "ok" and bool(secret)
    return {
        "provider": provider,
        "label": LABELS.get(provider, provider),
        "base_url": base,
        "has_secret": bool(secret),
        "masked_secret": mask(secret),
        "status": probe_status,
        "display_status": display_status(state),
        "detail": state.detail if state else "",
        "auth_method": state.auth_method if state else None,
        "access_verified": access_verified,
        "workflow_verified": False,
        "last_checked_at": _iso(state.last_checked_at) if state else None,
        "last_attempted_at": _iso(state.last_attempted_at) if state else None,
        "default_url": DEFAULTS.get(provider, ""),
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def merged_secret(previous: str, supplied: str | None) -> str:
    """Keep the stored secret when the form leaves the token blank."""
    if supplied is not None and supplied.strip():
        return supplied.strip()
    return previous or ""


def _stamp(status: str, now: datetime, previous: datetime | None) -> datetime | None:
    """Last successful contact is ok or reachable. Attempts are tracked separately."""
    if status in {"ok", "reachable"}:
        return now
    return previous


def apply_probe(
    previous: ConnectorState | None,
    *,
    provider: str,
    base_url: str,
    secret: str,
    auth_method: str | None,
    probe: Mapping[str, Any],
    now: datetime | None = None,
) -> ConnectorState:
    moment = now or datetime.now(timezone.utc)
    status = str(probe.get("status") or "error")
    detail = str(probe.get("detail") or "")
    prior_checked = previous.last_checked_at if previous else None
    return ConnectorState(
        provider=provider,
        base_url=base_url,
        secret=secret,
        status=status,
        detail=detail,
        auth_method=auth_method if secret else None,
        last_checked_at=_stamp(status, moment, prior_checked),
        last_attempted_at=moment,
    )


def apply_disconnect(previous: ConnectorState | None, provider: str, now: datetime | None = None) -> ConnectorState:
    moment = now or datetime.now(timezone.utc)
    base = previous.base_url if previous and previous.base_url else DEFAULTS.get(provider, "")
    return ConnectorState(
        provider=provider,
        base_url=base,
        secret="",
        status="disconnected",
        detail="Credentials removed. Configure and verify to reconnect.",
        auth_method=None,
        last_checked_at=previous.last_checked_at if previous else None,
        last_attempted_at=moment,
    )


def response_payload(state: ConnectorState, probe: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    """Safe API body after a mutation. No secret, no pairing code."""
    body = {
        "ok": state.status in {"ok", "reachable"},
        "status": state.status,
        "detail": state.detail,
        "display_status": display_status(state),
        "access_verified": bool(probe.get("access_verified")),
        "workflow_verified": False,
        "extra": probe.get("extra") or {},
        "base_url": state.base_url,
        "has_secret": bool(state.secret),
    }
    body.update(extra)
    return body
