"""Reusable auth flows for SelfRepair (register / verify / forgot / reset).

These are pure-ish functions that operate on request data and the database,
reusing the project's existing primitives (``redis_client`` tokens + rate
limiting, ``email_service`` delivery, ``security`` hashing/creation and the
``User`` model). They are shared by both the legacy Jinja form handlers in
``main.py`` and the JSON ``/v1/auth/*`` endpoints in ``api_v1.py`` so the two
surfaces keep IDENTICAL semantics (validation, neutral responses that don't
leak account existence, email-verification gating, encrypted secrets, never
surfacing reset links).

Nothing here imports ``main`` so there is no circular-import risk.
"""
from __future__ import annotations

import os
import re

from . import email_service, redis_client
from .database import AuditLog, SessionLocal, User
from .security import create_user, hash_password

# --------------------------------------------------------------------------
# Constants (mirrors of the values previously living only in main.py)
# --------------------------------------------------------------------------
APP_BASE_URL = os.environ.get(
    "APP_BASE_URL", "https://ruslanmv-selfrepair.hf.space"
).rstrip("/")
VERIFY_TTL = 24 * 3600
RESET_TTL = 3600

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


# --------------------------------------------------------------------------
# Shared validation / audit helpers
# --------------------------------------------------------------------------

def password_problem(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


def audit(action: str, user_id: str | None = None, ip: str | None = None, details: str | None = None) -> None:
    db = SessionLocal()
    try:
        db.add(AuditLog(user_id=user_id, action=action, ip_address=ip, details=details))
        db.commit()
    finally:
        db.close()


def issue_verification(user) -> str:
    """Mint a verification token and send the confirmation email.

    Returns the verification link (callers MUST NOT surface it to anonymous
    users; it is returned only for demo-mode/Jinja parity).
    """
    token = redis_client.put_token("verify", user.id, VERIFY_TTL)
    link = f"{APP_BASE_URL}/verify?token={token}"
    email_service.send_verification_email(user.email, link)
    return link


# --------------------------------------------------------------------------
# Flows — return small result dicts the caller maps to JSON / Jinja.
# --------------------------------------------------------------------------

class AuthError(Exception):
    """Raised when a flow fails with a user-facing message + HTTP status."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def register(username: str, email: str, password: str, ip: str | None = None) -> dict:
    """Create an unverified user and issue a verification email.

    Raises ``AuthError`` on validation failures (400) or duplicates (409).
    Returns ``{"email", "delivery", "link"}`` on success.
    """
    username = (username or "").strip()
    email = (email or "").strip().lower()

    if not USERNAME_RE.match(username):
        raise AuthError(400, "Username must be 3–32 chars (letters, numbers, . _ -).")
    if not EMAIL_RE.match(email):
        raise AuthError(400, "Enter a valid email address.")
    problem = password_problem(password)
    if problem:
        raise AuthError(400, problem)

    db = SessionLocal()
    try:
        if db.query(User).filter((User.email == email) | (User.username == username)).first():
            raise AuthError(409, "Username or email already taken.")
    finally:
        db.close()

    user = create_user(username=username, email=email, password=password)
    link = issue_verification(user)
    audit("register", user_id=user.id, ip=ip, details=email)
    return {
        "email": email,
        "delivery": email_service.configured(),
        "link": link,
    }


def resend_verification(email: str) -> None:
    """Re-issue a verification email if an unverified user exists.

    Always silent (neutral response is the caller's job) — never reveals
    whether the email exists.
    """
    email = (email or "").strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user and not user.email_verified:
            db.expunge(user)
            issue_verification(user)
    finally:
        db.close()


def verify(token: str) -> None:
    """Consume a verify token and mark the user verified.

    Raises ``AuthError(400)`` on invalid/expired token.
    """
    user_id = redis_client.pop_token("verify", token or "")
    if not user_id:
        raise AuthError(400, "This verification link is invalid or has expired.")
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            raise AuthError(400, "This verification link is invalid or has expired.")
        user.email_verified = True
        db.add(AuditLog(user_id=user.id, action="email_verified"))
        db.commit()
    finally:
        db.close()


def forgot_password(email: str, ip: str | None = None) -> None:
    """Email a reset link if the account exists. Never surfaces the link.

    Always silent — neutral response is the caller's job.
    """
    email = (email or "").strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user:
            token = redis_client.put_token("reset", user.id, RESET_TTL)
            link = f"{APP_BASE_URL}/reset-password?token={token}"
            email_service.send_reset_email(user.email, link)
            audit("password_reset_requested", user_id=user.id, ip=ip)
    finally:
        db.close()


def reset_password(token: str, password: str) -> None:
    """Consume a reset token and set the new password (also verifies email).

    Raises ``AuthError(400)`` on weak password or invalid/expired token.
    """
    problem = password_problem(password)
    if problem:
        raise AuthError(400, problem)

    user_id = redis_client.pop_token("reset", token or "")
    if not user_id:
        raise AuthError(400, "This reset link is invalid or has expired.")

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            raise AuthError(400, "This reset link is invalid or has expired.")
        user.password_hash = hash_password(password)
        user.email_verified = True  # proves email ownership
        db.add(AuditLog(user_id=user.id, action="password_reset"))
        db.commit()
    finally:
        db.close()
