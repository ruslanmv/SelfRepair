"""GitHub App authentication.

Avoids long-lived PATs (system-design.md §7). The flow:

1. App identifier + private key are loaded from env or a secret manager.
2. To act as the app, mint a JWT signed with the private key (10 min TTL).
3. To act as an installation, POST to GitHub with the app JWT and receive
   an installation access token (1h TTL).
4. Tokens are cached with a 5-minute safety margin so we refresh before they
   expire.

Webhook signature verification uses HMAC-SHA256 with the per-app webhook
secret to confirm the payload is from GitHub. Constant-time comparison is
used to avoid timing attacks.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import httpx
import jwt as pyjwt

logger = logging.getLogger(__name__)

_TOKEN_REFRESH_MARGIN_SECONDS = 5 * 60


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        margin = timedelta(seconds=_TOKEN_REFRESH_MARGIN_SECONDS)
        return datetime.now(UTC) + margin >= self.expires_at


class GitHubAppAuth:
    """Mint app JWTs and installation tokens for GitHub API calls."""

    def __init__(
        self,
        *,
        app_id: str,
        private_key_pem: str,
        api_url: str = "https://api.github.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key_pem
        self._api_url = api_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._tokens: dict[int, InstallationToken] = {}
        self._lock = asyncio.Lock()

    def app_jwt(self) -> str:
        """Mint a short-lived JWT identifying the app itself.

        `iat` is backdated 60s to absorb clock skew between us and GitHub.
        `exp` is 9 minutes (GitHub's max is 10).
        """
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 9 * 60,
            "iss": self._app_id,
        }
        return pyjwt.encode(payload, self._private_key, algorithm="RS256")

    async def installation_token(self, installation_id: int) -> str:
        """Return a cached or freshly minted installation access token."""
        async with self._lock:
            cached = self._tokens.get(installation_id)
            if cached is not None and not cached.is_expired:
                return cached.token

            url = (
                f"{self._api_url}/app/installations/"
                f"{installation_id}/access_tokens"
            )
            resp = await self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.app_jwt()}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            token = InstallationToken(
                token=data["token"],
                expires_at=datetime.fromisoformat(
                    data["expires_at"].replace("Z", "+00:00")
                ),
            )
            self._tokens[installation_id] = token
            return token.token

    async def aclose(self) -> None:
        await self._client.aclose()


def verify_webhook_signature(
    *, secret: bytes | str, payload: bytes, header: str | None
) -> bool:
    """Verify GitHub's `X-Hub-Signature-256` against the raw body.

    Returns True iff the signature is well-formed and matches.
    """
    if not header or not header.startswith("sha256="):
        return False
    expected = header.split("=", 1)[1]
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    digest = hmac.new(secret, payload, sha256).hexdigest()
    return hmac.compare_digest(digest, expected)
