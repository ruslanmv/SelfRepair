"""Resolve reviewer credentials without logging secret values.

GitHub publication prefers a GitHub App installation token minted for the
repository's installation id. A static token is the fallback for a deployment
that has not installed the app. GitLab uses `GITLAB_TOKEN`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from selfrepair.auth.github_app import GitHubAppAuth

logger = logging.getLogger(__name__)


def first_env(*names: str) -> str:
    """Return the first non-empty environment value among `names`."""
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def github_app_from_env() -> GitHubAppAuth | None:
    """Build a GitHub App client when the id and private key are configured."""
    app_id = first_env("GITHUB_APP_ID", "SELFREPAIR_GITHUB_APP_ID")
    private_key = _private_key()
    if not app_id or not private_key:
        return None
    api_url = first_env("GITHUB_API_URL", "SELFREPAIR_GITHUB_API_URL") or "https://api.github.com"
    return GitHubAppAuth(app_id=app_id, private_key_pem=private_key, api_url=api_url)


def static_github_token() -> str:
    """A personal or pre-minted token. Empty when the operator did not set one."""
    return first_env("SELFREPAIR_GITHUB_TOKEN", "GITHUB_TOKEN")


def gitlab_token() -> str:
    """GitLab API token. Empty when publication cannot leave the process."""
    return first_env("GITLAB_TOKEN", "SELFREPAIR_GITLAB_TOKEN")


def gitlab_api_url() -> str:
    """GitLab origin. The API prefix is added by the publisher."""
    return (first_env("GITLAB_URL", "SELFREPAIR_GITLAB_URL") or "https://gitlab.com").rstrip("/")


def credential_status() -> dict[str, bool]:
    """Booleans only. Safe to log at worker startup."""
    app_id = first_env("GITHUB_APP_ID", "SELFREPAIR_GITHUB_APP_ID")
    return {
        "github_app": bool(app_id and _private_key()),
        "github_token": bool(static_github_token()),
        "gitlab_token": bool(gitlab_token()),
        "review_model": bool(first_env("SELFREPAIR_REVIEW_MODEL")),
        "ollabridge_url": bool(
            first_env(
                "SELFREPAIR_OLLABRIDGE_URL",
                "OLLABRIDGE_BASE_URL",
                "OPENAI_BASE_URL",
            )
        ),
    }


async def github_token_for(
    installation_id: int | None,
    *,
    app: GitHubAppAuth | None = None,
) -> str:
    """Mint an installation token, then fall back to a static token.

    A mint failure is logged without the response body and does not raise.
    The caller treats an empty string as "cannot read or publish".
    """
    client = app if app is not None else github_app_from_env()
    if client is not None and installation_id is not None:
        try:
            return await client.installation_token(int(installation_id))
        except Exception:
            logger.warning(
                "github installation token mint failed installation=%s",
                installation_id,
            )
    return static_github_token()


def _private_key() -> str:
    path = first_env("GITHUB_APP_PRIVATE_KEY_PATH", "SELFREPAIR_GITHUB_APP_PRIVATE_KEY_PATH")
    if path:
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            logger.warning("github app private key file is unreadable")
    inline = first_env("GITHUB_APP_PRIVATE_KEY", "SELFREPAIR_GITHUB_APP_PRIVATE_KEY")
    return inline.replace("\\n", "\n")
