"""Session cookie helpers.

`secure` is on by default in any non-dev environment. The cookie is
httpOnly + SameSite=Lax + path=/ so it cannot be read by JS, can't
leak across sites in standard navigations, and applies to every API
route under the same origin.
"""
from __future__ import annotations

import os

from fastapi import Response

COOKIE_NAME = "selfrepair_session"


def is_secure_default() -> bool:
    """Production cookies must be Secure. Dev/test override via env."""
    return (
        os.getenv("SELFREPAIR_ENV", "dev").lower()
        not in {"dev", "test", "local", "ci"}
    )


def set_session_cookie(
    response: Response, token: str, *, max_age_seconds: int
) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        secure=is_secure_default(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME, path="/", samesite="lax", httponly=True,
        secure=is_secure_default(),
    )
