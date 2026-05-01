"""Authentication and security utilities."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone

from .database import SessionLocal, User

# Secret key for session signing (generated at startup if not set)
SECRET_KEY = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
TOKEN_PEPPER = os.environ.get("TOKEN_PEPPER", "repoguardian-hf-default-pepper")


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt, dk_hex = stored_hash.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False


def generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(48)


def authenticate_user(email_or_username: str, password: str) -> User | None:
    """Authenticate user by email/username and password."""
    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter((User.email == email_or_username) | (User.username == email_or_username))
            .first()
        )
        if user and verify_password(password, user.password_hash):
            user.last_login = datetime.now(timezone.utc)
            db.commit()
            db.refresh(user)
            return user
        return None
    finally:
        db.close()


def create_user(username: str, email: str, password: str, role: str = "user") -> User:
    """Create a new user account."""
    db = SessionLocal()
    try:
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            display_name=username,
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()
